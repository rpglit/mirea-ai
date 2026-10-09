const fs = require("fs");
const katex = require("/opt/katex/node_modules/katex");

const [stringsPath, outPath] = [process.argv[2], process.argv[3]];
const strings = JSON.parse(fs.readFileSync(stringsPath, "utf8"));
const result = { total: 0, ok: 0, failed: [], warnings: 0, sample: strings.slice(0, 5) };

for (const s of strings) {
  for (const mode of [false, true]) {
    result.total += 1;
    try {
      katex.renderToString(s, {
        displayMode: mode,
        throwOnError: true,
        onWarning: () => {
          result.warnings += 1;
        },
      });
      result.ok += 1;
    } catch (err) {
      result.failed.push({
        tex: s.slice(0, 200),
        mode: mode ? "display" : "inline",
        error: String((err && err.message) || err),
      });
    }
  }
}

fs.writeFileSync(outPath, JSON.stringify(result, null, 1));
console.log(
  `rendered ${result.ok}/${result.total} ok, ${result.failed.length} failed, ${result.warnings} warnings`
);
process.exit(result.failed.length ? 1 : 0);
