INSERT INTO public.topics (name, name_hi) VALUES ('Crime & Law', 'अपराध व कानून') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Economy', 'अर्थव्यवस्था') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Entertainment', 'मनोरंजन') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Environment', 'पर्यावरण') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Health', 'स्वास्थ्य') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('International', 'अंतरराष्ट्रीय') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Politics', 'राजनीति') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Science & Tech', 'विज्ञान व तकनीक') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Society', 'समाज') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;

INSERT INTO public.topics (name, name_hi) VALUES ('Sports', 'खेल') ON CONFLICT (name) DO UPDATE SET name_hi = EXCLUDED.name_hi;
