import type { BuildingStructure } from "./campusBuildingsStructureTypes"

export const CAMPUS_STRUCTURE_ACADEMIC: BuildingStructure[] = [
  /* ── А — Главный учебный корпус (ГУК, стр. 8, 8 этажей) ── */
  {
    letter: "ГУК",
    structureId: "стр. 8",
    tags: ["study", "services", "events"],
    geoCoords: [55.71405, 37.81165],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ГУК-101", number: "101", type: "lecture", capacity: 200 },
          { id: "ГУК-102", number: "102", type: "cafeteria", capacity: 300 },
          { id: "ГУК-103", number: "103", type: "admin", capacity: 20 },
          { id: "ГУК-104", number: "104", type: "other", capacity: 15 },
          { id: "ГУК-105", number: "105", type: "admin", capacity: 12 },
          { id: "ГУК-106", number: "106", type: "lecture", capacity: 100 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ГУК-201", number: "201", type: "lecture", capacity: 120 },
          { id: "ГУК-202", number: "202", type: "seminar", capacity: 40 },
          { id: "ГУК-203", number: "203", type: "office", capacity: 10 },
          { id: "ГУК-204", number: "204", type: "seminar", capacity: 35 },
          { id: "ГУК-205", number: "205", type: "seminar", capacity: 30 },
          { id: "ГУК-229", number: "229", type: "admin", capacity: 15 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "ГУК-301", number: "301", type: "lecture", capacity: 80 },
          { id: "ГУК-302", number: "302", type: "seminar", capacity: 30 },
          { id: "ГУК-303", number: "303", type: "office", capacity: 8 },
          { id: "ГУК-304", number: "304", type: "seminar", capacity: 30 },
          { id: "ГУК-305", number: "305", type: "seminar", capacity: 35 },
          { id: "ГУК-310", number: "310", type: "lab", capacity: 25 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "ГУК-401", number: "401", type: "lecture", capacity: 80 },
          { id: "ГУК-402", number: "402", type: "seminar", capacity: 35 },
          { id: "ГУК-403", number: "403", type: "seminar", capacity: 30 },
          { id: "ГУК-410", number: "410", type: "office", capacity: 10 },
          { id: "ГУК-464", number: "464", type: "office", capacity: 12 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "ГУК-501", number: "501", type: "seminar", capacity: 30 },
          { id: "ГУК-502", number: "502", type: "office", capacity: 10 },
          { id: "ГУК-506", number: "506", type: "admin", capacity: 15 },
          { id: "ГУК-507", number: "507", type: "office", capacity: 12 },
          { id: "ГУК-509", number: "509", type: "admin", capacity: 10 },
          { id: "ГУК-515", number: "515", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 6,
        rooms: [
          { id: "ГУК-601", number: "601", type: "seminar", capacity: 30 },
          { id: "ГУК-602", number: "602", type: "office", capacity: 10 },
          { id: "ГУК-610", number: "610", type: "office", capacity: 8 },
        ],
      },
      {
        floor: 7,
        rooms: [
          { id: "ГУК-701", number: "701", type: "office", capacity: 8 },
          { id: "ГУК-702", number: "702", type: "office", capacity: 8 },
          { id: "ГУК-705", number: "705", type: "admin", capacity: 6 },
        ],
      },
      {
        floor: 8,
        rooms: [
          { id: "ГУК-801", number: "801", type: "office", capacity: 6 },
          { id: "ГУК-802", number: "802", type: "admin", capacity: 10 },
        ],
      },
    ],
  },

  /* ── Б — Корпус поточных аудиторий + Библиотека (стр. 5, 5 этажей) ── */
  {
    letter: "ПА",
    structureId: "стр. 5",
    tags: ["study", "services"],
    geoCoords: [55.7135, 37.81669],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ПА-101", number: "101", type: "lecture", capacity: 250 },
          { id: "ПА-102", number: "102", type: "lecture", capacity: 200 },
          { id: "ПА-103", number: "103", type: "lecture", capacity: 150 },
          { id: "ПА-104", number: "104", type: "admin", capacity: 10 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ПА-201", number: "201", type: "lecture", capacity: 150 },
          { id: "ПА-202", number: "202", type: "library", capacity: 100 },
          { id: "ПА-203", number: "203", type: "study", capacity: 50 },
          { id: "ПА-204", number: "204", type: "study", capacity: 40 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "ПА-301", number: "301", type: "lecture", capacity: 120 },
          { id: "ПА-302", number: "302", type: "seminar", capacity: 40 },
          { id: "ПА-303", number: "303", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "ПА-401", number: "401", type: "seminar", capacity: 40 },
          { id: "ПА-402", number: "402", type: "seminar", capacity: 35 },
          { id: "ПА-403", number: "403", type: "lecture", capacity: 80 },
          { id: "ПА-410", number: "410", type: "seminar", capacity: 30 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "ПА-501", number: "501", type: "office", capacity: 15 },
          { id: "ПА-502", number: "502", type: "office", capacity: 10 },
          { id: "ПА-503", number: "503", type: "seminar", capacity: 25 },
        ],
      },
    ],
  },

  /* ── В — Лабораторный корпус + Приёмная комиссия (стр. 4, 6 этажей) ── */
  {
    letter: "ЛК",
    structureId: "стр. 4",
    tags: ["study", "services"],
    geoCoords: [55.71342, 37.81537],
    floors: [
      {
        floor: 1,
        rooms: [
          { id: "ЛК-101", number: "101", type: "admin", capacity: 20 },
          { id: "ЛК-102", number: "102", type: "lab", capacity: 30 },
          { id: "ЛК-103", number: "103", type: "lab", capacity: 25 },
          { id: "ЛК-104", number: "104", type: "seminar", capacity: 40 },
        ],
      },
      {
        floor: 2,
        rooms: [
          { id: "ЛК-201", number: "201", type: "lab", capacity: 20 },
          { id: "ЛК-202", number: "202", type: "lab", capacity: 25 },
          { id: "ЛК-204", number: "204", type: "lab", capacity: 25 },
          { id: "ЛК-206", number: "206", type: "lab", capacity: 20 },
          { id: "ЛК-207", number: "207", type: "seminar", capacity: 30 },
          { id: "ЛК-212", number: "212", type: "lab", capacity: 20 },
          { id: "ЛК-216", number: "216", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 3,
        rooms: [
          { id: "ЛК-301", number: "301", type: "lab", capacity: 20 },
          { id: "ЛК-302", number: "302", type: "lab", capacity: 20 },
          { id: "ЛК-304", number: "304", type: "office", capacity: 12 },
          { id: "ЛК-308", number: "308", type: "office", capacity: 10 },
          { id: "ЛК-310", number: "310", type: "office", capacity: 10 },
          { id: "ЛК-312", number: "312", type: "office", capacity: 12 },
        ],
      },
      {
        floor: 4,
        rooms: [
          { id: "ЛК-401", number: "401", type: "lab", capacity: 25 },
          { id: "ЛК-402", number: "402", type: "office", capacity: 12 },
          { id: "ЛК-410", number: "410", type: "seminar", capacity: 30 },
          { id: "ЛК-431", number: "431", type: "office", capacity: 10 },
          { id: "ЛК-440", number: "440", type: "seminar", capacity: 35 },
        ],
      },
      {
        floor: 5,
        rooms: [
          { id: "ЛК-501", number: "501", type: "office", capacity: 10 },
          { id: "ЛК-502", number: "502", type: "office", capacity: 8 },
          { id: "ЛК-510", number: "510", type: "seminar", capacity: 25 },
        ],
      },
      {
        floor: 6,
        rooms: [
          { id: "ЛК-601", number: "601", type: "office", capacity: 8 },
          { id: "ЛК-602", number: "602", type: "office", capacity: 6 },
          { id: "ЛК-645", number: "645", type: "office", capacity: 15 },
        ],
      },
    ],
  },
]
