import type { ChatLocation, LocationInfo, Poi } from '../types';

interface PoiContext {
  location?: ChatLocation;
  location_info?: LocationInfo;
}

function buildPoiUrl(p: Poi, ctx?: PoiContext): string {
  const city = ctx?.location_info?.city || '';
  const name = encodeURIComponent(p.name);
  if (p.location && /^[\d.]+,[\d.]+$/.test(p.location)) {
    return `https://uri.amap.com/marker?position=${p.location}&name=${name}&src=travelagent&coordinate=gaode`;
  }
  return `https://www.amap.com/search?query=${name}${city ? `&city=${encodeURIComponent(city)}` : ''}`;
}

export function linkifyPois(
  html: string,
  pois: Poi[],
  ctx?: PoiContext,
): string {
  if (!pois?.length) return html;

  const sorted = [...pois]
    .filter((p) => p?.name && p.name.length >= 2)
    .sort((a, b) => b.name.length - a.name.length);
  if (!sorted.length) return html;

  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  const skipTags = new Set(['A', 'PRE', 'CODE', 'SCRIPT', 'STYLE']);

  function walk(node: Node): void {
    if (node.nodeType === Node.TEXT_NODE) {
      const txt = node.textContent || '';
      if (!txt) return;
      let pos = 0;
      const frag = document.createDocumentFragment();
      let changed = false;
      while (pos < txt.length) {
        let nextIdx = -1;
        let nextPoi: Poi | null = null;
        for (const p of sorted) {
          const idx = txt.indexOf(p.name, pos);
          if (idx >= 0 && (nextIdx === -1 || idx < nextIdx)) {
            nextIdx = idx;
            nextPoi = p;
            if (idx === pos) break;
          }
        }
        if (nextPoi === null) {
          frag.appendChild(document.createTextNode(txt.slice(pos)));
          break;
        }
        if (nextIdx > pos) {
          frag.appendChild(document.createTextNode(txt.slice(pos, nextIdx)));
        }
        const a = document.createElement('a');
        a.href = buildPoiUrl(nextPoi, ctx);
        a.target = '_blank';
        a.rel = 'noopener';
        a.className = 'poi-link';
        a.textContent = nextPoi.name;
        frag.appendChild(a);
        pos = nextIdx + nextPoi.name.length;
        changed = true;
      }
      if (changed && node.parentNode) {
        node.parentNode.replaceChild(frag, node);
      }
      return;
    }
    if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as Element;
      if (skipTags.has(el.tagName)) return;
      const children = [...el.childNodes];
      for (const ch of children) walk(ch);
    }
  }

  walk(tpl.content);
  const wrap = document.createElement('div');
  wrap.appendChild(tpl.content.cloneNode(true));
  return wrap.innerHTML;
}

export function formatLocationPlace(info?: LocationInfo | null): string {
  if (!info) return '';
  return `${info.city || ''}${info.district || ''}${info.township || ''}`.trim();
}
