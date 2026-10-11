"""Minimal stdlib-only text extractor for text-based (ReportLab-style) PDFs.

Returns a list of page strings. Handles ASCII85 + Flate filters and Tj/TJ
text operators, which is sufficient for the deal-room pack. A production
build would swap this for a robust parser/OCR service.
"""
import base64
import re
import zlib

_OBJ_RE = re.compile(rb"(\d+)\s+0\s+obj(.*?)endobj", re.S)
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)


def _decode_stream(dict_part, raw):
    filters = re.findall(rb"/(ASCII85Decode|FlateDecode)", dict_part)
    data = raw
    for f in filters:
        if f == b"ASCII85Decode":
            data = data.strip()
            if data.startswith(b"<~"):
                data = data[2:]
            if data.endswith(b"~>"):
                data = data[:-2]
            data = base64.a85decode(data)
        elif f == b"FlateDecode":
            data = zlib.decompress(data)
    return data


def _unescape(s):
    out, i = bytearray(), 0
    esc = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
           b"(": b"(", b")": b")", b"\\": b"\\"}
    while i < len(s):
        c = s[i:i + 1]
        if c == b"\\" and i + 1 < len(s):
            n = s[i + 1:i + 2]
            if n in esc:
                out += esc[n]; i += 2; continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(), 8) & 0xFF); i += 1 + len(m.group()); continue
            i += 1; continue
        out += c; i += 1
    return out.decode("cp1252", errors="replace")


def _content_to_text(content):
    lines, cur = [], []
    # Tokenise text operators line by line: BT/ET, Td/TD/T*/', Tj, TJ
    for m in re.finditer(rb"\((?:\\.|[^\\)])*\)\s*Tj|\[(.*?)\]\s*TJ|T\*|Td|TD|ET", content, re.S):
        tok = m.group(0)
        if tok.endswith(b"Tj"):
            cur.append(_unescape(tok[1:tok.rindex(b")")]))
        elif tok.endswith(b"TJ"):
            parts = re.findall(rb"\(((?:\\.|[^\\)])*)\)", m.group(1))
            cur.append("".join(_unescape(p) for p in parts))
        else:
            if cur:
                lines.append("".join(cur)); cur = []
    if cur:
        lines.append("".join(cur))
    return "\n".join(l.rstrip() for l in lines)


def extract_pages(path):
    data = open(path, "rb").read()
    objs = {int(m.group(1)): m.group(2) for m in _OBJ_RE.finditer(data)}
    # Page order from the /Kids array of the root /Pages object
    kids = []
    for body in objs.values():
        if re.search(rb"/Type\s*/Pages\b", body):
            k = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
            if k:
                kids = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", k.group(1))]
                break
    pages = []
    for pid in kids:
        body = objs.get(pid, b"")
        refs = re.search(rb"/Contents\s*(\[(.*?)\]|(\d+)\s+0\s+R)", body, re.S)
        ids = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", refs.group(0))] if refs else []
        text = []
        for cid in ids:
            obj = objs.get(cid, b"")
            sm = _STREAM_RE.search(obj)
            if not sm:
                continue
            content = _decode_stream(obj[:sm.start()], sm.group(1))
            text.append(_content_to_text(content))
        pages.append("\n".join(text))
    return pages


if __name__ == "__main__":
    import sys
    for i, p in enumerate(extract_pages(sys.argv[1]), 1):
        print(f"===== PAGE {i} =====\n{p}")
