"""
test_offsite_backup.py - the off-machine backup tool, tested WITHOUT any real credentials or upload.

Covers: (1) request signing against AWS's published SigV4 test vector; (2) the encryption format
(round trip, wrong passphrase, bit-flip, truncation, chunk reordering, ciphertext hides the plaintext);
(3) a full backup -> encrypted upload -> retention -> restore-test cycle against an in-process fake S3
server that RE-VERIFIES every signature and payload hash; (4) failure modes (bad credentials, tampered
object, wrong passphrase leave no temp files and fail loudly); (5) configuration rules (credentials may not
live in the repo; unconfigured = no network, exit 2); (6) the scheduled-job wiring is conditional.

Run:  py test_offsite_backup.py
"""
import hashlib
import http.server
import os
import re
import socketserver
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

import offsite_backup as ob

FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


# ============================================================================ 1. SigV4 test vector
print("=== 1. request signing matches AWS's published test vector ===")
# https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html  ("GET Object" example)
auth = ob.sigv4_authorization(
    "GET", "/test.txt", {},
    {"Host": "examplebucket.s3.amazonaws.com", "Range": "bytes=0-9",
     "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "x-amz-date": "20130524T000000Z"},
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", "20130524T000000Z")
check("1: GET Object example reproduces AWS's documented signature",
      auth.endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
      and "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in auth)
auth2 = ob.sigv4_authorization(
    "GET", "/", {"lifecycle": ""},
    {"Host": "examplebucket.s3.amazonaws.com",
     "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "x-amz-date": "20130524T000000Z"},
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", "20130524T000000Z")
check("2: GET Bucket Lifecycle example (query string) reproduces AWS's documented signature",
      auth2.endswith("Signature=fea454ca298b7da1c68078a5d1bdbfbbe0d65c699e0f91ac7a200a0136783543"))

# ==================================================================================== 2. encryption
print("\n=== 2. encryption format ===")
PASS = "correct horse battery staple 42"
tmp = Path(tempfile.mkdtemp(prefix="pk_ob_"))
plain = (b"SQLite format 3\x00 secret row: Paksh corpus " * 400) + os.urandom(3000)
src = tmp / "in.db"
src.write_bytes(plain)
enc, out = tmp / "x.enc", tmp / "out.db"
st = ob.compress_encrypt(src, enc, PASS, chunk=256)                # tiny chunks -> many chunks
n = ob.decrypt_decompress(enc, out, PASS)
check("3: round trip restores the exact bytes across many chunks", out.read_bytes() == plain and n == len(plain))
check("4: the stored file hides the plaintext (no SQLite magic, no readable row text)",
      b"SQLite format 3" not in enc.read_bytes() and b"secret row" not in enc.read_bytes())
check("5: plaintext sha256 recorded by the writer matches", st["plain_sha256"] == hashlib.sha256(plain).hexdigest())


def fails(path, passphrase=PASS):
    try:
        ob.decrypt_decompress(path, tmp / "junk.db", passphrase)
        return False
    except ValueError:
        return True


check("6: wrong passphrase is rejected", fails(enc, "not the passphrase at all 123"))
blob = bytearray(enc.read_bytes())
bit = tmp / "bit.enc"; b2 = bytearray(blob); b2[len(b2) // 2] ^= 0x01; bit.write_bytes(b2)
check("7: a single flipped bit anywhere is detected", fails(bit))
hdr, blk = ob.HEADER_LEN, 256 + ob.TAG
nblocks = (len(blob) - hdr + blk - 1) // blk
trunc = tmp / "trunc.enc"; trunc.write_bytes(blob[:hdr + (nblocks - 1) * blk])       # drop the final chunk cleanly
check("8: truncation at a chunk boundary is detected (last-chunk flag)", fails(trunc))
ext = tmp / "ext.enc"; ext.write_bytes(blob + os.urandom(blk))
check("9: appended data is detected", fails(ext))
swap = tmp / "swap.enc"; s = bytearray(blob)
a1, a2 = hdr, hdr + blk
s[a1:a1 + blk], s[a2:a2 + blk] = blob[a2:a2 + blk], blob[a1:a1 + blk]; swap.write_bytes(s)
check("10: reordering chunks is detected (counter in nonce + AAD)", fails(swap))
empty = tmp / "empty.db"; empty.write_bytes(b"")
ob.compress_encrypt(empty, tmp / "e.enc", PASS)
ob.decrypt_decompress(tmp / "e.enc", tmp / "e.out", PASS)
check("11: an empty file round-trips", (tmp / "e.out").read_bytes() == b"")
check("12: two encryptions of the same data differ (random salt/nonce)",
      (lambda a, b: a != b)(*[(ob.compress_encrypt(src, tmp / ("r%d.enc" % i), PASS, chunk=256), (tmp / ("r%d.enc" % i)).read_bytes())[1] for i in (1, 2)]))


# ====================================================================================== 3. fake S3
class FakeS3(http.server.BaseHTTPRequestHandler):
    store_dir = None
    secret = "SECRET"
    access = "AKID"
    region = "auto"
    objects = {}                                       # key -> (path, meta)
    lock = threading.Lock()
    reject_all = False

    def log_message(self, *a):
        pass

    def _verify(self, payload_hash):
        h = {k.lower(): v for k, v in self.headers.items()}
        m = re.match(r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, SignedHeaders=([^,]+), Signature=(\w+)", h.get("authorization", ""))
        if not m or m.group(1) != self.access or self.reject_all:
            return False
        signed = m.group(4).split(";")
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        expect = ob.sigv4_authorization(self.command, u.path, q, {k: h[k] for k in signed}, payload_hash, self.access,
                                        self.secret, m.group(3), h["x-amz-date"])
        return expect.endswith("Signature=" + m.group(5)) and h.get("x-amz-content-sha256") == payload_hash

    def _key(self):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        parts = path.lstrip("/").split("/", 1)
        return parts[1] if len(parts) > 1 else ""

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def do_PUT(self):
        n = int(self.headers.get("Content-Length", "0"))
        p = Path(self.store_dir) / hashlib.md5(self._key().encode()).hexdigest()
        part = p.with_name(p.name + ".part")                       # like real S3: an object appears only once verified
        h, sha = 0, hashlib.sha256()
        with open(part, "wb") as f:
            while h < n:
                blk = self.rfile.read(min(1 << 20, n - h)); f.write(blk); sha.update(blk); h += len(blk)
        claimed = self.headers.get("x-amz-content-sha256")
        if not self._verify(claimed) or sha.hexdigest() != claimed:
            part.unlink(); return self._send(403, b"<Error>SignatureDoesNotMatch</Error>")
        os.replace(part, p)
        meta = {k.lower(): v for k, v in self.headers.items() if k.lower().startswith("x-amz-meta-")}
        with self.lock:
            self.objects[self._key()] = (p, meta)
        self._send(200)

    def do_GET(self):
        if not self._verify(hashlib.sha256(b"").hexdigest()):
            return self._send(403, b"<Error>SignatureDoesNotMatch</Error>")
        u = urllib.parse.urlparse(self.path)
        if not self._key():
            q = dict(urllib.parse.parse_qsl(u.query)); pre = q.get("prefix", "")
            body = "<ListBucketResult xmlns='http://s3.amazonaws.com/doc/2006-03-01/'><IsTruncated>false</IsTruncated>" + "".join(
                "<Contents><Key>%s</Key><LastModified>2026-09-19T00:00:00.000Z</LastModified><Size>%d</Size></Contents>" % (k, v[0].stat().st_size)
                for k, v in sorted(self.objects.items()) if k.startswith(pre)) + "</ListBucketResult>"
            return self._send(200, body.encode(), {"Content-Type": "application/xml"})
        o = self.objects.get(self._key())
        if not o:
            return self._send(404, b"<Error>NoSuchKey</Error>")
        data = o[0].read_bytes()
        self._send(200, data, dict(o[1]))

    def do_HEAD(self):
        if not self._verify(hashlib.sha256(b"").hexdigest()):
            return self._send(403)
        o = self.objects.get(self._key())
        if not o:
            return self._send(404)
        hh = dict(o[1]); self.send_response(200)
        for k, v in hh.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(o[0].stat().st_size)); self.end_headers()

    def do_DELETE(self):
        if not self._verify(hashlib.sha256(b"").hexdigest()):
            return self._send(403)
        with self.lock:
            o = self.objects.pop(self._key(), None)
        if o:
            o[0].unlink()
        self._send(204)


FakeS3.store_dir = tempfile.mkdtemp(prefix="pk_s3_")
srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeS3)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]
CFG = {"S3_ENDPOINT": "http://127.0.0.1:%d" % PORT, "S3_BUCKET": "paksh-backups", "S3_REGION": "auto",
       "S3_ACCESS_KEY_ID": "AKID", "S3_SECRET_ACCESS_KEY": "SECRET", "BACKUP_PASSPHRASE": PASS, "S3_PREFIX": "",
       "_path": str(tmp / "cfg.env")}


def make_db(path, events=40, articles=300):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, title TEXT)")
    c.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, event_id INTEGER)")
    c.executemany("INSERT INTO events(title) VALUES (?)", [("story %d confidential-marker" % i,) for i in range(events)])
    c.executemany("INSERT INTO articles(title, event_id) VALUES (?,?)", [("article %d" % i, i % events) for i in range(articles)])
    c.commit(); c.close()


print("\n=== 3. full cycle against a fake S3 that re-verifies signatures ===")
bdir = tmp / "backups"; bdir.mkdir()
localdb = bdir / "paksh_backup_20260919_120000.db"
make_db(localdb)
os.environ["PAKSH_OFFSITE_TMP"] = str(tmp)
logs = []
key1 = ob.run_backup(CFG, source=localdb, keep=2, allow_old=True, log=logs.append)
stored = Path(FakeS3.store_dir) / hashlib.md5(key1.encode()).hexdigest()
raw = stored.read_bytes()
check("13: backup was uploaded and the server verified our signature and payload hash", key1 in FakeS3.objects)
check("14: the object at rest is ciphertext (no SQLite magic, no row text)",
      b"SQLite format 3" not in raw and b"confidential-marker" not in raw and raw.startswith(ob.MAGIC))
check("15: object metadata carries only counts (events/articles), not content",
      FakeS3.objects[key1][1].get("x-amz-meta-events") == "40" and FakeS3.objects[key1][1].get("x-amz-meta-articles") == "300")
check("16: no temp file is left behind after a successful run", not list(tmp.glob("paksh_offsite_*.enc")))
check("17: restore-test PASSES (download, decrypt, integrity_check, counts match)", ob.restore_test(CFG, log=logs.append))
dest = tmp / "restored.db"
r = ob.restore_to(CFG, key1, dest, log=logs.append)
c = sqlite3.connect(dest); back = c.execute("SELECT title FROM events WHERE id=1").fetchone()[0]; c.close()
check("18: a real restore reproduces the original data", r["ok"] and back == "story 0 confidential-marker")
try:
    ob.restore_to(CFG, key1, dest, log=logs.append); refused = False
except SystemExit:
    refused = True
check("19: restore refuses to overwrite an existing file", refused)

keys = [key1]
for _ in range(3):
    time.sleep(1.1)
    keys.append(ob.run_backup(CFG, source=localdb, keep=2, allow_old=True, log=logs.append))
left = sorted(k for k in FakeS3.objects if ob.KEY_RE.search(k))
check("20: retention keeps exactly the newest 2 and never deletes the one just uploaded", left == sorted(keys)[-2:])

print("\n=== 4. failure modes fail loudly ===")
bad = dict(CFG, S3_SECRET_ACCESS_KEY="WRONG")
try:
    ob.run_backup(bad, source=localdb, keep=2, allow_old=True, log=logs.append); failed = False
except ob.S3Error:
    failed = True
check("21: wrong credentials -> the upload is rejected and reported", failed)
check("22: ...and no plaintext/temp file is left behind", not list(tmp.glob("paksh_offsite_*.enc")))
check("23: restore-test FAILS with the wrong passphrase", not ob.restore_test(dict(CFG, BACKUP_PASSPHRASE="a different long passphrase!"), log=logs.append))
newest = FakeS3.objects[max(FakeS3.objects)][0]
b = bytearray(newest.read_bytes()); b[len(b) // 2] ^= 0xFF; newest.write_bytes(b)
check("24: restore-test FAILS if the stored object was altered", not ob.restore_test(CFG, log=logs.append))
FakeS3.objects.clear()
check("25: restore-test FAILS (not 'passes') when nothing is stored off-machine", not ob.restore_test(CFG, log=logs.append))

print("\n=== 5. configuration rules ===")
inrepo = dict(CFG, _path=str(ob.ROOT / "offsite_backup.env"))
check("26: a config file inside the repository is refused", any("inside the repository" in p for p in ob.config_problems(inrepo)))
check("27: missing credentials are named", "S3_ACCESS_KEY_ID" in " ".join(ob.config_problems({"_path": str(tmp / "c.env")})))
check("28: a non-local http:// endpoint is refused", any("https" in p for p in ob.config_problems(dict(CFG, S3_ENDPOINT="http://example.com"))))
check("29: a short passphrase is refused", any("shorter" in p for p in ob.config_problems(dict(CFG, BACKUP_PASSPHRASE="short"))))
os.environ["PAKSH_OFFSITE_ENV"] = str(tmp / "does_not_exist.env")
for k in ob.REQUIRED:
    os.environ.pop(k, None)
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = ob.main(["--run"])
check("30: unconfigured --run exits 2, uploads nothing, and prints the one manual step",
      rc == 2 and "NOT configured" in buf.getvalue() and "BACKUP_PASSPHRASE" in buf.getvalue())

print("\n=== 6. scheduled-job wiring ===")
bat = (Path(__file__).parent / "reframe_scheduled.bat").read_text(encoding="utf-8", errors="replace")
check("31: the job runs offsite_backup.py only if the config file exists",
      re.search(r'if exist "%LOCALAPPDATA%\\Paksh\\offsite_backup\.env" py offsite_backup\.py --run', bat) is not None)
check("32: the off-site step comes after the local backup step",
      bat.index("backup_db.py --keep 5") < bat.index("offsite_backup.py --run"))

srv.shutdown()
print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("ALL ASSERTIONS PASSED")
