"use strict"

// Adapted from micromatch 4.0.8 index.js (isMatch, capture, makeRe).
// Copyright (c) 2014-present, Jon Schlinkert. MIT license: see LICENSE.
// https://github.com/micromatch/micromatch/blob/4.0.8/index.js
// Only the APIs used by eslint-plugin-boundaries 7.2.0 and
// @boundaries/elements 3.1.1 are supported. See README.md before extending.
const picomatch = require("picomatch")
const utils = require("picomatch/lib/utils")

exports.isMatch = (str, patterns, options) => picomatch(patterns, options)(str)

exports.capture = (glob, input, options) => {
  const posix = utils.isWindows(options)
  const regex = picomatch.makeRe(String(glob), { ...options, capture: true })
  const match = regex.exec(posix ? utils.toPosixSlashes(input) : input)

  if (match) {
    return match.slice(1).map((value) => (value === undefined ? "" : value))
  }
}

exports.makeRe = (...args) => picomatch.makeRe(...args)
