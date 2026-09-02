import type { BuildingStructure } from "./campusBuildingsStructureTypes"

export const CAMPUS_STRUCTURE_RESIDENTIAL: BuildingStructure[] = [
  /* ── Ж — Общежитие №2 + ЦУВП (стр. 2, 16 этажей) ── */
  {
    letter: "О2",
    structureId: "стр. 2",
    tags: ["housing", "events"],
    geoCoords: [55.71384, 37.81577],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "О2-101", number: "101", type: "study", capacity: 20 },
          { id: "О2-102", number: "102", type: "cafeteria", capacity: 40 },
          { id: "О2-103", number: "103", type: "admin", capacity: 8 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "О2-201", number: "201", type: "study", capacity: 15 },
          { id: "О2-202", number: "202", type: "other", capacity: 10 },
          { id: "О2-203", number: "203", type: "other", capacity: 100 },
        ],
      },
    ],
  },

  /* ── З — Общежитие №6 (к. 6, 18 этажей) ── */
  {
    letter: "О6",
    structureId: "к. 6",
    tags: ["housing"],
    geoCoords: [55.71495, 37.81547],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "О6-101", number: "101", type: "study", capacity: 25 },
          { id: "О6-102", number: "102", type: "cafeteria", capacity: 50 },
          { id: "О6-103", number: "103", type: "admin", capacity: 6 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "О6-201", number: "201", type: "study", capacity: 20 },
          { id: "О6-202", number: "202", type: "other", capacity: 15 },
        ],
      },
    ],
  },

  /* ── И — Бизнес-центр (стр. 16, 2+ этажа) ── */
  {
    letter: "ЦИТ",
    structureId: "стр. 16",
    tags: ["study", "services"],
    geoCoords: [55.71569, 37.81355],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ЦИТ-101", number: "101", type: "seminar", capacity: 30 },
          { id: "ЦИТ-102", number: "102", type: "office", capacity: 10 },
          { id: "ЦИТ-103", number: "103", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ЦИТ-201", number: "201", type: "seminar", capacity: 25 },
          { id: "ЦИТ-202", number: "202", type: "office", capacity: 8 },
          { id: "ЦИТ-205", number: "205", type: "office", capacity: 10 },
        ],
      },
    ],
  },
]
