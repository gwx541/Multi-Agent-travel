const XHS_HOST_RE =
  /^https?:\/\/[^/\s]*?(xiaohongshu\.com|xhslink\.com)\b/i;
const HOTEL_HOST_RE =
  /^https?:\/\/[^/\s]*?(ctrip\.com|trip\.com|elong\.com|rollinggo\.cn|aigohotel\.com)\b/i;
const TRAIN_HOST_RE = /^https?:\/\/[^/\s]*?12306\.cn\b/i;

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[
        c
      ] || c,
  );
}

function classifyLink(url: string): string | null {
  if (XHS_HOST_RE.test(url)) return 'xhs-link';
  if (HOTEL_HOST_RE.test(url)) return 'hotel-link';
  if (TRAIN_HOST_RE.test(url)) return 'train-link';
  return null;
}

export function renderMarkdown(md: string): string {
  if (!md) return '';
  let src = md;
  src = src.replace(/!\[[^\]]*\]\([^)]+\)/g, '');

  const safeLinks: { text: string; url: string; cls: string }[] = [];
  src = src.replace(
    /\[([^\]\n]+)\]\((https?:[^)\s]+)\)/g,
    (_m, text: string, url: string) => {
      const cls = classifyLink(url);
      if (cls) {
        safeLinks.push({ text, url, cls });
        return `\u0000XL${safeLinks.length - 1}\u0000`;
      }
      return text;
    },
  );
  src = src.replace(/(?<![\w/])https?:\/\/\S+/g, (m) => {
    const cls = classifyLink(m);
    if (cls) {
      const fallbackText =
        cls === 'xhs-link'
          ? '小红书笔记'
          : cls === 'hotel-link'
            ? '携程酒店'
            : '12306 购票';
      safeLinks.push({ text: fallbackText, url: m, cls });
      return `\u0000XL${safeLinks.length - 1}\u0000`;
    }
    return '';
  });

  const codeBlocks: string[] = [];
  src = src.replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, (_m, code: string) => {
    codeBlocks.push(
      `<pre><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`,
    );
    return `\u0000CB${codeBlocks.length - 1}\u0000`;
  });

  const inlineCodes: string[] = [];
  src = src.replace(/`([^`\n]+)`/g, (_m, c: string) => {
    inlineCodes.push(`<code>${escapeHtml(c)}</code>`);
    return `\u0000IC${inlineCodes.length - 1}\u0000`;
  });

  function inline(s: string): string {
    s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
    s = s.replace(/(?<![*\w])\*([^*\n]+)\*(?![*\w])/g, '<em>$1</em>');
    s = s.replace(/(?<![_\w])_([^_\n]+)_(?![_\w])/g, '<em>$1</em>');
    return s;
  }

  function cell(text: string): string {
    return inline(escapeHtml(text));
  }

  function splitRow(line: string): string[] {
    return line
      .replace(/^\s*\|/, '')
      .replace(/\|\s*$/, '')
      .split('|')
      .map((s) => s.trim());
  }

  const blockStarter =
    /^(#{1,6}\s|\s*>|\s*\|.*\|\s*$|\s*[-*+]\s|\s*\d+\.\s|\s{0,3}[-*_]{3,}\s*$|```)/;

  const lines = src.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const lv = Math.min(heading[1].length + 1, 4);
      out.push(`<h${lv}>${cell(heading[2])}</h${lv}>`);
      i++;
      continue;
    }
    if (/^\s{0,3}[-*_]{3,}\s*$/.test(line)) {
      out.push('<hr>');
      i++;
      continue;
    }
    if (line.trim().startsWith('>')) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        buf.push(lines[i].replace(/^\s*>\s?/, ''));
        i++;
      }
      out.push(`<blockquote>${cell(buf.join(' '))}</blockquote>`);
      continue;
    }
    if (
      /^\s*\|.*\|\s*$/.test(line) &&
      i + 1 < lines.length &&
      /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])
    ) {
      const head = splitRow(lines[i]);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      let t =
        '<table><thead><tr>' +
        head.map((c) => `<th>${cell(c)}</th>`).join('') +
        '</tr></thead><tbody>';
      for (const r of rows) {
        t += `<tr>${r.map((c) => `<td>${cell(c)}</td>`).join('')}</tr>`;
      }
      t += '</tbody></table>';
      out.push(t);
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ''));
        i++;
      }
      out.push(
        `<ul>${items.map((it) => `<li>${cell(it)}</li>`).join('')}</ul>`,
      );
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      out.push(
        `<ol>${items.map((it) => `<li>${cell(it)}</li>`).join('')}</ol>`,
      );
      continue;
    }
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !blockStarter.test(lines[i])) {
      buf.push(lines[i]);
      i++;
    }
    out.push(`<p>${buf.map((l) => cell(l)).join('<br>')}</p>`);
  }

  let html = out.join('');
  html = html.replace(/\u0000IC(\d+)\u0000/g, (_m, n) => inlineCodes[+n]);
  html = html.replace(/\u0000CB(\d+)\u0000/g, (_m, n) => codeBlocks[+n]);
  html = html.replace(/\u0000XL(\d+)\u0000/g, (_m, n) => {
    const it = safeLinks[+n];
    return `<a class="${it.cls}" href="${escapeHtml(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.text)} ↗</a>`;
  });
  html = html.replace(/<p>(\s*<pre>[\s\S]*?<\/pre>\s*)<\/p>/g, '$1');
  return html;
}

export { escapeHtml };
