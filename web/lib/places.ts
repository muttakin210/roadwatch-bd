// Offline place search for Bangladesh: ~50,000 towns, villages, upazilas, districts, markets, stations and
// airports from GeoNames (CC BY 4.0), in /geo/bd-places.json. The service worker keeps a copy, so search works
// without internet. Bangla names exist for the larger places only.
export type Place = { name: string; bn: string; lat: number; lng: number; kind: string; division: string; pop: number };

let loading: Promise<Place[]> | null = null;

export function loadPlaces(): Promise<Place[]> {
  loading ??= fetch("/geo/bd-places.json")
    .then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json() as Promise<{ rows: [string, string, number, number, string, string, number][] }>;
    })
    .then((d) => d.rows.map(([name, bn, lat, lng, kind, division, pop]) => ({ name, bn: bn.normalize("NFC"), lat, lng, kind, division, pop })))
    .catch((e) => {
      loading = null; // let a later search try again (e.g. once back online)
      throw e;
    });
  return loading;
}

const fold = (s: string) => s.normalize("NFC").toLowerCase().replace(/[^\p{L}\p{M}\p{N}]+/gu, " ").trim();

/** Best matches first: exact name, then names starting with the query, then containing it; bigger places first. */
export function searchPlaces(all: Place[], query: string, limit = 10): Place[] {
  const q = fold(query);
  if (q.length < 2) return [];
  const scored: [number, Place][] = [];
  for (const p of all) {
    let best = 0;
    for (const n of [p.name, p.bn]) {
      if (!n) continue;
      const f = fold(n);
      const s = f === q ? 3 : f.startsWith(q) ? 2 : f.includes(q) ? 1 : 0;
      if (s > best) best = s;
    }
    if (best) scored.push([best, p]);
  }
  scored.sort((a, b) => b[0] - a[0] || b[1].pop - a[1].pop);
  return scored.slice(0, limit).map((x) => x[1]);
}

/** The ~60 largest towns and cities, labelled on the offline map (as HTML, which renders Bangla correctly). */
export function majorPlaces(all: Place[], n = 60): Place[] {
  return all.filter((p) => p.kind.startsWith("PPL")).sort((a, b) => b.pop - a.pop).slice(0, n);
}
