/* Quick clean (NO AI): removes exact repeated lines, in the browser.
 * Mirrors backend/compactor.py dedupe(): code blocks untouched, short lines kept,
 * near-duplicates only counted (never deleted). Works without any server. */
(function () {
  "use strict";

  function norm(line) {
    return line.toLowerCase().replace(/[^\p{L}\p{N}_\s]/gu, "").replace(/\s+/g, " ").trim();
  }
  function shingles(words) {
    var set = new Set();
    if (words.length <= 3) { set.add(words.join(" ")); return set; }
    for (var i = 0; i <= words.length - 3; i++) set.add(words.slice(i, i + 3).join(" "));
    return set;
  }

  function dedupe(text) {
    var out = [], seen = new Set(), sigs = [];
    var removed = 0, removedChars = 0, similar = 0, inCode = false;
    var lines = String(text).split(/\r?\n/);
    for (var k = 0; k < lines.length; k++) {
      var line = lines[k].replace(/\s+$/, "");
      if (/^\s*```/.test(line)) { inCode = !inCode; out.push(line); continue; }
      if (inCode) { out.push(line); continue; }
      var n = norm(line);
      if (n.length < 25) { out.push(line); continue; }
      if (seen.has(n)) { removed++; removedChars += line.length + 1; continue; }
      var words = n.split(" ");
      if (words.length >= 8 && sigs.length < 3000) {
        var sh = shingles(words);
        for (var j = 0; j < sigs.length; j++) {
          var ratio = sigs[j][0] / words.length;
          if (ratio >= 0.8 && ratio <= 1.25) {
            var inter = 0;
            sh.forEach(function (x) { if (sigs[j][1].has(x)) inter++; });
            var union = sh.size + sigs[j][1].size - inter;
            if (inter && inter / union >= 0.9) { similar++; break; }
          }
        }
        sigs.push([words.length, sh]);
      }
      seen.add(n);
      out.push(line);
    }
    return { text: out.join("\n").replace(/\n{3,}/g, "\n\n").trim(), removed: removed, removedChars: removedChars, similar: similar };
  }

  window.CompactionClean = { dedupe: dedupe };
})();
