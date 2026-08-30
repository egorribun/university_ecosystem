import type { BuildingStructure } from "./campusBuildingsStructureTypes"

export const CAMPUS_STRUCTURE_ADMINISTRATIVE: BuildingStructure[] = [
  /* ── Г — Административный корпус (стр. 1, 5 этажей) ── */
  {
    letter: "А",
    structureId: "стр. 1",
    tags: ["services"],
    geoCoords: [55.71401, 37.81778],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "А-101", number: "101", type: "admin", capacity: 15 },
          { id: "А-102", number: "102", type: "admin", capacity: 10 },
          { id: "А-105", number: "105", type: "other", capacity: 8 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "А-201", number: "201", type: "admin", capacity: 12 },
          { id: "А-202", number: "202", type: "office", capacity: 8 },
          { id: "А-203", number: "203", type: "office", capacity: 6 },
          { id: "А-210", number: "210", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "А-301", number: "301", type: "admin", capacity: 15 },
          { id: "А-302", number: "302", type: "office", capacity: 8 },
          { id: "А-319", number: "319", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "А-401", number: "401", type: "office", capacity: 10 },
          { id: "А-402", number: "402", type: "office", capacity: 8 },
          { id: "А-405", number: "405", type: "admin", capacity: 8 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "А-501", number: "501", type: "office", capacity: 8 },
          { id: "А-502", number: "502", type: "office", capacity: 6 },
        ],
      },
    ],
  },

  /* ── Д — Бассейн ГУУ (к. 3, 2 этажа, построен 2013) ── */
  {
    letter: "Б",
    structureId: "к. 3",
    tags: ["sports"],
    geoCoords: [55.71572, 37.81193],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "Б-101", number: "101", type: "sports", capacity: 60 },
          { id: "Б-102", number: "102", type: "other", capacity: 20 },
          { id: "Б-103", number: "103", type: "office", capacity: 6 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "Б-201", number: "201", type: "sports", capacity: 30 },
          { id: "Б-202", number: "202", type: "other", capacity: 15 },
        ],
      },
    ],
  },

  /* ── Е — Спортивный комплекс (стр. 7, 2 этажа) ── */
  {
    letter: "СК",
    structureId: "стр. 7",
    tags: ["sports", "events"],
    geoCoords: [55.7149, 37.81272],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "СК-101", number: "101", type: "sports", capacity: 200 },
          { id: "СК-102", number: "102", type: "sports", capacity: 80 },
          { id: "СК-103", number: "103", type: "other", capacity: 15 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "СК-201", number: "201", type: "sports", capacity: 40 },
          { id: "СК-202", number: "202", type: "sports", capacity: 30 },
          { id: "СК-203", number: "203", type: "sports", capacity: 25 },
        ],
      },
    ],
  },
]
