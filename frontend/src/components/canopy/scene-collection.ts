/**
 * The four Zambian photographs behind the welcome composer. All CC BY-SA 4.0
 * from Wikimedia Commons; the interface names the photographer beside the
 * active view and links the source page and licence (Delso's requested
 * delso.photo credit included). Display copies are resized only, hosted in
 * the public site-assets bucket so the app bundle stays small; the untouched
 * original is linked from the source page.
 */
export interface Scene {
  id: string
  title: string
  caption: string
  description: string
  author: string
  authorUrl?: string
  source: string
  license: string
  licenseUrl: string
  dimensions: [number, number]
  /** Focal point for portrait framing on phones. */
  focus: string
}

const SUPABASE = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
export const PHOTO_BASE = `${SUPABASE}/storage/v1/object/public/site-assets/canopy/photos`
export const PHOTO_WIDTHS = [640, 960, 1600, 2560] as const

export function photoSrc(id: string, width: (typeof PHOTO_WIDTHS)[number]) {
  return `${PHOTO_BASE}/${id}-${width}.webp`
}
export function photoSrcSet(id: string) {
  return PHOTO_WIDTHS.map((w) => `${photoSrc(id, w)} ${w}w`).join(', ')
}

const LICENSE = 'CC BY-SA 4.0'
const LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'

export const SCENES: Scene[] = [
  {
    id: 'kafue-river',
    title: 'Along the Kafue',
    caption: 'Mumbwa · Zambia',
    description: 'A wide, calm stretch of the Kafue River framed by reeds and trees under a blue sky.',
    author: 'Timothy A. Gonsalves',
    source: 'https://commons.wikimedia.org/wiki/File:Kafue_River_Pinnon_Lodge_Zambia_Jul23_A7C_05318.jpg',
    license: LICENSE,
    licenseUrl: LICENSE_URL,
    dimensions: [6000, 4000],
    focus: '43% 50%',
  },
  {
    id: 'victoria-falls',
    title: 'Victoria Falls',
    caption: 'Zambia–Zimbabwe',
    description: 'An aerial photograph of Victoria Falls and the Zambezi, with the full sweep of the waterfall and its gorge.',
    author: 'Diego Delso',
    authorUrl: 'https://delso.photo',
    source: 'https://commons.wikimedia.org/wiki/File:Cataratas_Victoria,_Zambia-Zimbabue,_2018-07-27,_DD_05.jpg',
    license: LICENSE,
    licenseUrl: LICENSE_URL,
    dimensions: [6819, 3891],
    focus: '52% 50%',
  },
  {
    id: 'luangwa-sunset',
    title: 'Evening on the Luangwa',
    caption: 'South Luangwa · Zambia',
    description: 'Warm sunset light reflected in the still Luangwa River, with dark trees along the far bank.',
    author: 'Timothy A. Gonsalves',
    source: 'https://commons.wikimedia.org/wiki/File:Sunset_Luangwa_River_Wide_Zambia_Jul23_A7C_05776.jpg',
    license: LICENSE,
    licenseUrl: LICENSE_URL,
    dimensions: [6000, 4000],
    focus: '54% 50%',
  },
  {
    id: 'lake-kashiba',
    title: 'Lake Kashiba',
    caption: 'Copperbelt · Zambia',
    description: 'The forest surrounding Lake Kashiba reflected in the lake beneath a softly lit cloudy sky.',
    author: 'Sybryn',
    source: 'https://commons.wikimedia.org/wiki/File:Lake_Kashiba_boundary.jpg',
    license: LICENSE,
    licenseUrl: LICENSE_URL,
    dimensions: [6000, 4000],
    focus: '50% 50%',
  },
]
