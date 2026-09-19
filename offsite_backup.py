#!/usr/bin/env python3
"""
offsite_backup.py - an encrypted, verified, OFF-MACHINE copy of paksh.db.

WHY: backups/ (backup_db.py) protects against corruption and bad migrations, but it sits on the SAME
disk as paksh.db. The accumulated corpus (~600k articles, months of history) cannot be re-collected, so
one disk failure would erase it. This copies the newest verified local backup to S3-compatible object
storage (Cloudflare R2, Backblaze B2, AWS S3, ...) - compressed, then encrypted ON THIS MACHINE before
anything leaves it. The storage provider only ever sees ciphertext.

    py offsite_backup.py --check                # config + key + connectivity (tiny test object). Uploads NO data.
    py offsite_backup.py --run                  # compress + encrypt + upload newest local backup, verify, apply retention
    py offsite_backup.py --restore-test         # download newest, decrypt, integrity_check, compare counts, delete temp
    py offsite_backup.py --list                 # what is stored off-machine
    py offsite_backup.py --restore KEY --to D:\\restore\\paksh.db     # real restore (never overwrites an existing file)

NOTHING is uploaded until you create the config file (see "ONE MANUAL STEP" below). Until then --run
prints what is missing and exits 2, and the scheduled job skips this step entirely.

ONE MANUAL STEP (needs your accounts - nothing here can invent them)
  1. Create a bucket at Cloudflare R2 (10 GB free, no egress fee) or Backblaze B2, and an API token that is
     scoped to THAT bucket only, with read+write (no account-wide admin).
  2. Create  %LOCALAPPDATA%\\Paksh\\offsite_backup.env  (outside the repo - this script refuses a config
     inside the repository) containing:
         S3_ENDPOINT=https://<accountid>.r2.cloudflarestorage.com      (R2)   or  https://s3.<region>.backblazeb2.com (B2)
         S3_BUCKET=paksh-backups
         S3_REGION=auto                                                (R2: auto ; B2: e.g. us-west-004)
         S3_ACCESS_KEY_ID=...
         S3_SECRET_ACCESS_KEY=...
         BACKUP_PASSPHRASE=<a long random passphrase - 20+ characters>
         KEEP=7                                                        (optional; newest N backups are kept; default 7)
  3. Put a COPY of BACKUP_PASSPHRASE in your password manager. **If it is lost the backups are
     unrecoverable** - that is what makes them private, and there is no recovery path.
  4. Run:  py offsite_backup.py --check    then    py offsite_backup.py --run    then    py offsite_backup.py --restore-test

Security notes: encryption is AES-256-GCM, chunked (4 MiB) with per-chunk authentication and a
last-chunk flag, so tampering, reordering and truncation are all detected on restore. The key is derived
from the passphrase with scrypt (random 16-byte salt per backup). Only object size and the row counts
(events/articles) are stored in the clear, as object metadata, so a restore can be checked.
"""
import argparse
import hashlib
import hmac
import http.client
import os
import re
import socket
import sqlite3
import struct
import sys
import tempfile
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_DIR = ROOT / "backups"
CHUNK = 4 * 1024 * 1024                    # plaintext bytes per encrypted chunk
TAG = 16                                   # AES-GCM tag
MAGIC = b"PKBK1\n"
HEADER_LEN = len(MAGIC) + 16 + 4 + 1 + 4   # magic, salt, nonce prefix, log2(scrypt N), chunk size
SCRYPT_LOG_N = 15
KEY_RE = re.compile(r"paksh_\d{8}_\d{6}\.db\.gz\.enc$")
LOCAL_RE = re.compile(r"^paksh_backup_\d{8}_\d{6}\.db$")
REQUIRED = ["S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "BACKUP_PASSPHRASE"]


# ------------------------------------------------------------------------------------------ config
def config_path() -> Path:
    p = os.environ.get("PAKSH_OFFSITE_ENV")
    if p:
        return Path(p)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".config")
    return Path(base) / "Paksh" / "offsite_backup.env"


def load_config(path: Path = None) -> dict:
    """KEY=VALUE file (outside the repo) overlaid by real environment variables. Never printed."""
    path = path or config_path()
    cfg = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in REQUIRED + ["S3_REGION", "S3_PREFIX", "KEEP"]:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    cfg["_path"] = str(path)
    return cfg


def config_problems(cfg: dict) -> list:
    probs = []
    p = Path(cfg.get("_path", "")).resolve() if cfg.get("_path") else None
    if p and ROOT in p.parents:
        probs.append("the config file is inside the repository (%s); credentials must live OUTSIDE it" % p)
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        probs.append("missing: " + ", ".join(missing))
    if cfg.get("BACKUP_PASSPHRASE") and len(cfg["BACKUP_PASSPHRASE"]) < 12:
        probs.append("BACKUP_PASSPHRASE is shorter than 12 characters")
    ep = cfg.get("S3_ENDPOINT", "")
    if ep:
        u = urllib.parse.urlparse(ep)
        local = (u.hostname or "") in ("127.0.0.1", "localhost")
        if u.scheme != "https" and not (u.scheme == "http" and local):
            probs.append("S3_ENDPOINT must be https:// (plain http is only allowed for localhost tests)")
    return probs


MANUAL_STEP = """
Off-machine backup is NOT configured yet, so nothing was uploaded. The one manual step:
  1. Create an R2 or B2 bucket + a bucket-scoped read/write API token.
  2. Create %s
     with S3_ENDPOINT, S3_BUCKET, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, BACKUP_PASSPHRASE.
  3. Save a copy of BACKUP_PASSPHRASE in your password manager (lost = unrecoverable).
  4. py offsite_backup.py --check ; py offsite_backup.py --run ; py offsite_backup.py --restore-test
(details: docs/BACKUP_AND_RESTORE.md)"""


# -------------------------------------------------------------------------------- AWS SigV4 (stdlib)
def _hm(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _q(s: str, safe: str = "-_.~") -> str:
    return urllib.parse.quote(s, safe=safe)


def sigv4_authorization(method, canonical_uri, query, headers, payload_hash, access_key, secret_key,
                        region, amzdate, service="s3"):
    """AWS Signature V4. `headers` are the headers to sign (any case). `query` is a dict. Returns the
    Authorization header value. Verified against AWS's published test vectors (see the unit test)."""
    h = {k.lower(): " ".join(str(v).split()) for k, v in headers.items()}
    names = sorted(h)
    canon_headers = "".join("%s:%s\n" % (k, h[k]) for k in names)
    signed = ";".join(names)
    cq = "&".join("%s=%s" % (_q(k), _q(str(v))) for k, v in sorted((query or {}).items()))
    creq = "\n".join([method, canonical_uri, cq, canon_headers, signed, payload_hash])
    datestamp = amzdate[:8]
    scope = "%s/%s/%s/aws4_request" % (datestamp, region, service)
    sts = "\n".join(["AWS4-HMAC-SHA256", amzdate, scope, hashlib.sha256(creq.encode("utf-8")).hexdigest()])
    k = _hm(("AWS4" + secret_key).encode("utf-8"), datestamp)
    for part in (region, service, "aws4_request"):
        k = _hm(k, part)
    sig = hmac.new(k, sts.encode("utf-8"), hashlib.sha256).hexdigest()
    return "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (access_key, scope, signed, sig)


class S3Error(RuntimeError):
    pass


class S3:
    """Minimal path-style S3 client: PUT (streamed from a file), GET (streamed to a file), HEAD, DELETE, LIST."""

    def __init__(self, endpoint, bucket, region, access_key, secret_key, timeout=300):
        u = urllib.parse.urlparse(endpoint)
        self.scheme, self.host = u.scheme, u.netloc
        self.bucket, self.region = bucket, region or "auto"
        self.ak, self.sk, self.timeout = access_key, secret_key, timeout

    def _conn(self):
        cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return cls(self.host, timeout=self.timeout)

    def _path(self, key):
        return "/%s/%s" % (_q(self.bucket), _q(key, safe="/-_.~")) if key else "/%s" % _q(self.bucket)

    def _request(self, method, key="", query=None, body_path=None, body=b"", meta=None,
                 payload_hash=None, stream_to=None, ok=(200, 204), retries=3):
        query = query or {}
        size = os.path.getsize(body_path) if body_path else len(body)
        if payload_hash is None:
            payload_hash = hashlib.sha256(body).hexdigest() if not body_path else _sha256_file(body_path)
        last = None
        for attempt in range(retries):
            amzdate = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            hdrs = {"host": self.host, "x-amz-date": amzdate, "x-amz-content-sha256": payload_hash}
            for k, v in (meta or {}).items():
                hdrs["x-amz-meta-" + k] = str(v)
            uri = self._path(key)
            auth = sigv4_authorization(method, uri, query, hdrs, payload_hash, self.ak, self.sk, self.region, amzdate)
            path = uri + (("?" + "&".join("%s=%s" % (_q(k), _q(str(v))) for k, v in sorted(query.items()))) if query else "")
            conn = self._conn()
            try:
                conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
                for k, v in hdrs.items():
                    conn.putheader(k, v)
                conn.putheader("Authorization", auth)
                if method in ("PUT", "POST"):
                    conn.putheader("Content-Length", str(size))
                conn.endheaders()
                if body_path:
                    with open(body_path, "rb") as f:
                        while True:
                            blk = f.read(1024 * 1024)
                            if not blk:
                                break
                            conn.send(blk)
                elif body:
                    conn.send(body)
                r = conn.getresponse()
                if r.status in ok:
                    if stream_to is not None:
                        with open(stream_to, "wb") as out:
                            while True:
                                blk = r.read(1024 * 1024)
                                if not blk:
                                    break
                                out.write(blk)
                        data = b""
                    else:
                        data = r.read()
                    return r.status, dict((k.lower(), v) for k, v in r.getheaders()), data
                data = r.read()
                if r.status >= 500:
                    last = S3Error("HTTP %s %s" % (r.status, data[:160]))
                else:
                    raise S3Error("HTTP %s %s" % (r.status, data[:300].decode("utf-8", "replace")))
            except (OSError, http.client.HTTPException, socket.timeout) as e:
                last = S3Error("network: %s" % e)
            finally:
                conn.close()
            time.sleep(2 ** attempt)
        raise last or S3Error("request failed")

    def put_file(self, key, path, meta=None):
        return self._request("PUT", key, body_path=path, meta=meta)

    def put_bytes(self, key, data, meta=None):
        return self._request("PUT", key, body=data, meta=meta)

    def get_file(self, key, dest):
        return self._request("GET", key, stream_to=dest)

    def get_bytes(self, key):
        return self._request("GET", key)[2]

    def head(self, key):
        return self._request("HEAD", key)[1]

    def delete(self, key):
        return self._request("DELETE", key)

    def list(self, prefix=""):
        out, token = [], None
        while True:
            q = {"list-type": "2", "prefix": prefix}
            if token:
                q["continuation-token"] = token
            data = self._request("GET", "", query=q)[2]
            root = ET.fromstring(data)
            strip = lambda t: t.split("}")[-1]
            for c in root:
                if strip(c.tag) == "Contents":
                    d = {strip(x.tag): (x.text or "") for x in c}
                    out.append({"key": d.get("Key", ""), "size": int(d.get("Size", "0") or 0), "modified": d.get("LastModified", "")})
            trunc = next((x.text for x in root if strip(x.tag) == "IsTruncated"), "false")
            token = next((x.text for x in root if strip(x.tag) == "NextContinuationToken"), None)
            if trunc != "true" or not token:
                return out


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()


def s3_from_config(cfg) -> S3:
    return S3(cfg["S3_ENDPOINT"], cfg["S3_BUCKET"], cfg.get("S3_REGION", "auto"), cfg["S3_ACCESS_KEY_ID"], cfg["S3_SECRET_ACCESS_KEY"])


# ------------------------------------------------------------------------ compress + encrypt + decrypt
def _aead(passphrase: str, salt: bytes, log_n: int):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    key = Scrypt(salt=salt, length=32, n=1 << log_n, r=8, p=1).derive(passphrase.encode("utf-8"))
    return AESGCM(key)


def compress_encrypt(src: Path, dest: Path, passphrase: str, chunk: int = CHUNK) -> dict:
    """gzip the file and write it as an authenticated-encrypted stream. Returns sizes and a plaintext sha256."""
    salt, prefix = os.urandom(16), os.urandom(4)
    header = MAGIC + salt + prefix + bytes([SCRYPT_LOG_N]) + struct.pack(">I", chunk)
    aead = _aead(passphrase, salt, SCRYPT_LOG_N)
    comp = zlib.compressobj(6, zlib.DEFLATED, 31)          # wbits 31 = gzip container
    buf, counter, plain_sha, plain_len = bytearray(), 0, hashlib.sha256(), 0

    def emit(out, data, last):
        nonlocal counter
        nonce = prefix + struct.pack(">Q", counter)
        aad = header + struct.pack(">Q", counter) + (b"\x01" if last else b"\x00")
        out.write(aead.encrypt(nonce, bytes(data), aad))
        counter += 1

    with open(src, "rb") as f, open(dest, "wb") as out:
        out.write(header)
        while True:
            blk = f.read(1024 * 1024)
            if not blk:
                break
            plain_sha.update(blk); plain_len += len(blk)
            buf += comp.compress(blk)
            while len(buf) > chunk:
                emit(out, buf[:chunk], False)
                del buf[:chunk]
        buf += comp.flush()
        while len(buf) > chunk:
            emit(out, buf[:chunk], False)
            del buf[:chunk]
        emit(out, buf, True)                                # final chunk (possibly empty) carries the last-flag
    return {"plain_bytes": plain_len, "plain_sha256": plain_sha.hexdigest(), "enc_bytes": dest.stat().st_size}


def decrypt_decompress(src: Path, dest: Path, passphrase: str) -> int:
    """Inverse of compress_encrypt. Raises ValueError on a wrong passphrase, any tampering, or truncation."""
    from cryptography.exceptions import InvalidTag
    with open(src, "rb") as f:
        header = f.read(HEADER_LEN)
        if len(header) != HEADER_LEN or header[:len(MAGIC)] != MAGIC:
            raise ValueError("not a Paksh backup file (bad header)")
        o = len(MAGIC)
        salt, prefix, log_n = header[o:o + 16], header[o + 16:o + 20], header[o + 20]
        chunk = struct.unpack(">I", header[o + 21:o + 25])[0]
        if log_n > 20 or chunk > 64 * 1024 * 1024:
            raise ValueError("implausible header parameters")
        aead = _aead(passphrase, salt, log_n)
        block = chunk + TAG
        dec = zlib.decompressobj(31)
        cur, counter, written = f.read(block), 0, 0
        if not cur:
            raise ValueError("empty backup body")
        with open(dest, "wb") as out:
            while cur:
                nxt = f.read(block)
                last = not nxt
                nonce = prefix + struct.pack(">Q", counter)
                aad = header + struct.pack(">Q", counter) + (b"\x01" if last else b"\x00")
                try:
                    plain = aead.decrypt(nonce, cur, aad)
                except InvalidTag:
                    raise ValueError("authentication failed: wrong passphrase, or the file was altered/truncated")
                data = dec.decompress(plain)
                out.write(data); written += len(data)
                cur, counter = nxt, counter + 1
            out.write(dec.flush())
        if not dec.eof:
            raise ValueError("compressed stream ended early (truncated backup)")
    return written


# ---------------------------------------------------------------------------------------- operations
def _counts(db: Path):
    c = sqlite3.connect("file:%s?mode=ro" % db.as_posix(), uri=True, timeout=60)
    try:
        return (c.execute("SELECT COUNT(*) FROM events").fetchone()[0], c.execute("SELECT COUNT(*) FROM articles").fetchone()[0])
    finally:
        c.close()


def newest_local_backup(directory: Path = BACKUP_DIR):
    files = sorted((p for p in directory.glob("paksh_backup_*.db") if LOCAL_RE.match(p.name)), key=lambda p: p.name)
    return files[-1] if files else None


def tmpdir():
    return Path(os.environ.get("PAKSH_OFFSITE_TMP") or tempfile.gettempdir())


def run_backup(cfg, source: Path = None, keep: int = None, s3: S3 = None, allow_old=False, log=print) -> str:
    """compress + encrypt + upload + verify + retention. Returns the object key."""
    s3 = s3 or s3_from_config(cfg)
    source = source or newest_local_backup()
    if not source or not source.exists():
        raise SystemExit("no local backup found - run: py backup_db.py")
    age_h = (time.time() - source.stat().st_mtime) / 3600
    if age_h > 48 and not allow_old:
        raise SystemExit("newest local backup is %.0fh old; run py backup_db.py first (or pass --allow-old)" % age_h)
    keep = int(keep or cfg.get("KEEP") or 7)
    events, articles = _counts(source)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    key = "%spaksh_%s.db.gz.enc" % (cfg.get("S3_PREFIX", ""), stamp)
    tmp = tmpdir() / ("paksh_offsite_%s.enc" % stamp)
    t0 = time.time()
    try:
        log("source: %s (%.0f MB, events=%d, articles=%d)" % (source.name, source.stat().st_size / 1e6, events, articles))
        st = compress_encrypt(source, tmp, cfg["BACKUP_PASSPHRASE"])
        log("compressed+encrypted: %.0f MB (%.0f%% of original) in %.0fs" % (st["enc_bytes"] / 1e6, 100 * st["enc_bytes"] / max(1, st["plain_bytes"]), time.time() - t0))
        t1 = time.time()
        s3.put_file(key, str(tmp), meta={"events": events, "articles": articles, "plain-bytes": st["plain_bytes"], "plain-sha256": st["plain_sha256"], "format": "PKBK1"})
        head = s3.head(key)
        if int(head.get("content-length", -1)) != st["enc_bytes"]:
            raise S3Error("uploaded size %s != local %s" % (head.get("content-length"), st["enc_bytes"]))
        log("uploaded %s (%.0f MB) in %.0fs, size verified" % (key, st["enc_bytes"] / 1e6, time.time() - t1))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    apply_remote_retention(s3, cfg.get("S3_PREFIX", ""), keep, key, log)
    return key


def apply_remote_retention(s3, prefix, keep, just_uploaded, log=print):
    objs = sorted((o for o in s3.list(prefix + "paksh_") if KEY_RE.search(o["key"])), key=lambda o: o["key"], reverse=True)
    for o in objs[keep:]:
        if o["key"] != just_uploaded:
            s3.delete(o["key"])
            log("retention: removed old off-machine backup %s" % o["key"])
    log("retention: keeping newest %d (%d present now)" % (keep, min(keep, len(objs))))


def restore_to(cfg, key, dest: Path, s3: S3 = None, log=print) -> dict:
    """Download, decrypt, decompress to `dest`; verify with integrity_check + counts vs object metadata."""
    s3 = s3 or s3_from_config(cfg)
    if dest.exists():
        raise SystemExit("refusing to overwrite existing %s" % dest)
    head = s3.head(key)
    enc = tmpdir() / ("paksh_restore_%d.enc" % os.getpid())
    try:
        t0 = time.time()
        s3.get_file(key, str(enc))
        log("downloaded %.0f MB in %.0fs" % (enc.stat().st_size / 1e6, time.time() - t0))
        n = decrypt_decompress(enc, dest, cfg["BACKUP_PASSPHRASE"])
    finally:
        try:
            enc.unlink()
        except OSError:
            pass
    c = sqlite3.connect("file:%s?mode=ro" % dest.as_posix(), uri=True, timeout=60)
    try:
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        c.close()
    ev, ar = _counts(dest)
    want_e, want_a = int(head.get("x-amz-meta-events", -1)), int(head.get("x-amz-meta-articles", -1))
    ok = integrity == "ok" and ev == want_e and ar == want_a and ev > 0 and ar > 0
    return {"ok": ok, "integrity": integrity, "events": ev, "articles": ar, "expected_events": want_e,
            "expected_articles": want_a, "bytes": n}


def restore_test(cfg, s3: S3 = None, key=None, log=print) -> bool:
    s3 = s3 or s3_from_config(cfg)
    objs = sorted((o for o in s3.list(cfg.get("S3_PREFIX", "") + "paksh_") if KEY_RE.search(o["key"])), key=lambda o: o["key"])
    if not objs and not key:
        log("RESTORE-TEST FAILED: no backups found off-machine")
        return False
    key = key or objs[-1]["key"]
    dest = tmpdir() / ("paksh_restoretest_%d.db" % os.getpid())
    try:
        r = restore_to(cfg, key, dest, s3, log)
    except Exception as e:
        log("RESTORE-TEST FAILED for %s: %s" % (key, e))
        return False
    finally:
        for p in (dest,):
            try:
                p.unlink()
            except OSError:
                pass
    log("restore-test %s: %s  integrity=%s events=%d/%d articles=%d/%d" % (
        "PASSED" if r["ok"] else "FAILED", key, r["integrity"], r["events"], r["expected_events"], r["articles"], r["expected_articles"]))
    return r["ok"]


def check(cfg, s3: S3 = None, log=print) -> bool:
    probs = config_problems(cfg)
    if probs:
        for p in probs:
            log("CONFIG PROBLEM: " + p)
        log(MANUAL_STEP % cfg.get("_path"))
        return False
    log("config OK (%s)" % cfg["_path"])
    salt = os.urandom(16)
    _aead(cfg["BACKUP_PASSPHRASE"], salt, SCRYPT_LOG_N)
    log("encryption key derivation OK")
    s3 = s3 or s3_from_config(cfg)
    k = "%spaksh_check_%d" % (cfg.get("S3_PREFIX", ""), int(time.time()))
    payload = os.urandom(32)
    s3.put_bytes(k, payload)
    ok = s3.get_bytes(k) == payload
    s3.delete(k)
    log("round-trip write/read/delete of a 32-byte test object: %s" % ("OK" if ok else "MISMATCH"))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description="Encrypted off-machine copy of paksh.db (see the module docstring)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--restore-test", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--restore", metavar="KEY")
    ap.add_argument("--to", metavar="PATH")
    ap.add_argument("--source")
    ap.add_argument("--keep", type=int)
    ap.add_argument("--allow-old", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    if config_problems(cfg):
        if a.check:
            return 0 if check(cfg) else 2
        for p in config_problems(cfg):
            print("CONFIG PROBLEM:", p)
        print(MANUAL_STEP % cfg.get("_path"))
        return 2
    try:
        if a.check:
            return 0 if check(cfg) else 1
        if a.run:
            run_backup(cfg, Path(a.source) if a.source else None, a.keep, allow_old=a.allow_old)
            return 0
        if a.restore_test:
            return 0 if restore_test(cfg) else 1
        if a.list:
            for o in sorted(s3_from_config(cfg).list(cfg.get("S3_PREFIX", "") + "paksh_"), key=lambda o: o["key"]):
                print("%s  %8.0f MB  %s" % (o["modified"][:19], o["size"] / 1e6, o["key"]))
            return 0
        if a.restore:
            if not a.to:
                print("--restore needs --to PATH")
                return 2
            r = restore_to(cfg, a.restore, Path(a.to))
            print("restored to %s: integrity=%s events=%d articles=%d %s" % (a.to, r["integrity"], r["events"], r["articles"], "OK" if r["ok"] else "CHECK FAILED"))
            return 0 if r["ok"] else 1
    except (S3Error, ValueError) as e:
        print("OFFSITE BACKUP FAILED:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
