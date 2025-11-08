export interface GenerateManifestOptions {
  publicDir?: string
  sourcePath?: string
  check?: boolean
}

export interface GenerateManifestResult {
  sourcePath: string
  publicDir: string
}

export declare function generateManifests(options?: GenerateManifestOptions): GenerateManifestResult
