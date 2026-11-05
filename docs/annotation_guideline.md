# Annotation guideline — v1 (draft)

*Write example images into this document before labelling starts (PLAN §4.3). Two people label
the same 50 frames and 30 events; below ~80 % agreement on events → fix the definitions first.*

Event definitions should match the **Road Transport Act 2018** and DMP traffic rules where
possible. Mark any place where this guideline and the law differ.

---

## 1. Vehicle classes (boxes)

Use the unified list (PLAN §4.4). One box per visible vehicle, tight around the **visible** part.

| Class | Includes | Don't confuse with |
|---|---|---|
| `person` | pedestrians, people standing on the road, rickshaw pullers **only if not on the rickshaw** | the rider/driver of a vehicle (part of the vehicle box) |
| `bicycle` | pedal cycles | `motorcycle` (engine, larger wheels/body) |
| `rickshaw` | cycle-rickshaw with passenger seat/hood | `rickshaw_van` (flat cargo bed, no seat) |
| `rickshaw_van` | flat-bed cargo / van rickshaw | `rickshaw` |
| `motorcycle` | motorbikes, scooters | `bicycle` |
| `easybike` | battery e-rickshaw / easybike (usually larger, enclosed roof, 6+ seats) | `cng_autorickshaw` (green/grey caged body, 3 seats) |
| `cng_autorickshaw` | CNG auto-rickshaw (green/grey, metal cage) | `easybike`, `leguna` |
| `leguna` | leguna, human hauler, tempo (rear-entry, bench seats) | `microbus`, `cng_autorickshaw` |
| `car` | sedans, hatchbacks, taxis | `microbus` |
| `microbus` | microbus, SUV, jeep, minivan | `car`, `leguna` |
| `bus` | **all buses**: city bus, minibus, double-decker, intercity | `truck` |
| `truck` | trucks, lorries, tankers | `pickup` |
| `pickup` | pickup, covered van | `truck` (bigger, separate cab) |
| `ambulance` | ambulance, fire service, police vehicles with lights | — |
| `other` | tractor, hand cart, animal cart, anything else | — |

**Partly hidden vehicles:** box only the visible part. Skip if less than ~25 % is visible or
smaller than ~12 px on its short side. **Crowds of people:** box each person you can separate;
skip dense blobs.

---

## 2. States

- **Stopped:** the ground point (bottom-middle of the box) moves less than about half a vehicle
  length over ≥ 1 s. Rolling slowly in a queue is *not* stopped.
- **Running lane:** any part of the carriageway where traffic normally drives. Bus bays,
  footpaths, parking strips and the kerb-side half-lane where vehicles visibly pull in are
  **not** running lanes.
- **Kerb gap:** distance from the vehicle's kerb-side edge (its *left* side, Bangladesh drives on the
  left) to the kerb, in bus-widths.

---

## 3. Events

Use the events sheet: `clip, type, start_s, end_s, track_id, notes`, one row per event.

### E1 — jam vs signal queue
- **Signal queue:** traffic stops at the **same line** each time (signal, traffic police), in
  regular stop–go cycles (~30–120 s), often while cross traffic moves. Label as `signal_queue`.
- **Jam:** stopped or crawling with **no regular cycle**, or the front of the queue isn't at a fixed
  line, lasting longer than one signal cycle. Label `jam`.
- **Start** = first moment ≥ 60 % of vehicles in view are stopped; **end** = when most are moving again.
- If the clip is too short to tell, label `unknown_stop`.

### E2 — bus stopping mid-road
A bus (any type) is **stopped ≥ 8 s in a running lane** (kerb gap > ~0.5 bus-width) **by choice**:
the lane ahead of it is moving or empty, and it isn't waiting at a red light.
- **Start** = the moment the bus stops; **end** = the moment it moves off (or leaves the view).
- **Not E2 (label as hard negatives):** bus pulled in to the kerb, even at an informal stop; bus stuck
  behind stopped traffic; bus in a signal queue.
- A jam **behind** the bus does **not** make it "not E2" — that jam is usually caused by the bus.
- Leguna/human hauler doing the same: E2 with `subtype=leguna`.

### E3 — wrong-way driving
A vehicle moves **against the direction traffic should flow** on that part of the road for
≥ 2 s and ≥ 1 vehicle length.
- **Not E3:** reversing (slow, short, still facing the right way) — label `reversing`;
  U-turns (smooth ~180° turn) — label `u_turn`; vehicles at junctions where direction is ambiguous.
- Note the class; rickshaws/cycles along the kerb edge go in the notes as `at_kerb`.

### Hard negatives (just as important)
Label these explicitly so they can be counted: `signal_queue`, `police_hold`, `bus_at_kerb`,
`u_turn`, `reversing`, `bus_stuck_in_traffic`.

---

## 4. Agreement check
1. Two labellers independently label the same 50 frames and 30 events.
2. Boxes: match at IoU ≥ 0.5; report per-class agreement.
3. Events: a match is the same vehicle (or same interval for E1) with ≥ 30 % time overlap and the same type.
4. Below ~80 % event agreement → discuss every disagreement, update this guideline (bump the version), repeat.

## Change log
- v1 — first draft from PLAN v2.1.
