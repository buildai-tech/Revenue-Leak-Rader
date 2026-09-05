del lines[start:end]
lines[start:start] = new_block
out = "\n".join(lines)
out = out + "\n"
out = out.replace("\u0302", "").replace("\uFF09", ")" ).replace("\uFF08", "(" ).replace("\uFF0C", ",")
f = io.open(p, "w", encoding="utf-8", newline="\n")
f.write(out
f.close()
print("SPLICED")