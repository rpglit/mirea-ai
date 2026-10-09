export function labelTex(name) {
  const m = /^([a-zA-Z]+)(\d+)$/.exec(String(name));
  if (!m) return String(name);
  return m[2].length > 1 ? `${m[1]}_{${m[2]}}` : `${m[1]}_${m[2]}`;
}

export function tupleToTex(vals) {
  return `\\left(${(vals || []).map((v) => String(v)).join(",")}\\right)`;
}

export function markingToTex(vals) {
  const parts = (vals || []).map((v) =>
    v === null || v === undefined ? "\\omega" : String(v)
  );
  return `\\left(${parts.join(",")}\\right)`;
}

export const omegaTupleToTex = markingToTex;

export const MATRIX_KEYS = new Set(["F", "B", "C", "D", "W_minus", "W_plus"]);

export function faEnumToTex(line) {
  const m = /^\s*([A-Za-z]\w*)\s*=\s*([φψ])\(([^)]*)\)\s*$/.exec(String(line));
  if (!m) return null;
  const args = m[3]
    .split(",")
    .map((part) => labelTex(part.trim()))
    .join(", ");
  const fn = m[2] === "φ" ? "\\varphi" : "\\psi";
  return `${labelTex(m[1])} = ${fn}(${args})`;
}

function cellToTex(v) {
  if (v === null || v === undefined) return "0";
  if (typeof v === "number") return String(v);
  const s = String(v);
  const m = /^(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)$/.exec(s);
  if (m) return `\\frac{${m[1]}}{${m[2]}}`;
  return s;
}

export function matrixToTex(rows) {
  const body = (rows || [])
    .map((row) => (row || []).map(cellToTex).join("&"))
    .join("\\\\");
  return `\\begin{pmatrix}${body}\\end{pmatrix}`;
}

export function ioToTex(map, prefix = "I") {
  return Object.keys(map || {})
    .sort()
    .map((t) => {
      const places = Object.keys(map[t] || {})
        .sort()
        .map((p) => {
          const w = map[t][p];
          const label = labelTex(p);
          return w === 1 ? label : `${label} \\times ${String(w)}`;
        })
        .join(", ");
      return `${prefix}(${labelTex(t)}) = \\{${places}\\}`;
    })
    .join("; ");
}
