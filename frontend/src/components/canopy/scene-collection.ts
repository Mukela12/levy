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
  /** The welcome line shown with this photograph. */
  headline: string
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

/**
 * How wide the welcome photograph is drawn. Phones are capped at the 960
 * variant: a background behind glass cards does not need retina sharpness,
 * and on Zambian mobile data 960 is a third of the 1600's weight.
 * The img and the preload below must use the same value.
 */
export const PHOTO_SIZES = '(max-width: 700px) 320px, (max-width: 1100px) 100vw, calc(100vw - 300px)'

const LICENSE = 'CC BY-SA 4.0'
const LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'

export const SCENES: Scene[] = [
  {
    id: 'kafue-river',
    headline: 'A clearer place to begin.',
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
    headline: 'Ask, with the sources in reach.',
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
    headline: 'Zambian law, plainly answered.',
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
    headline: 'Begin with a question.',
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

/**
 * Parse-time preload for the welcome photograph. The chat page is prerendered
 * at build time, so a preload chosen during render names the build hour's
 * photograph, and phones downloaded a wrong 350KB image on most visits. This
 * runs in the browser before first paint, picks the same scene the welcome
 * will (same stored preference, same hourly formula), and preloads exactly
 * the size the img will request.
 */
export const sceneBootScript = `(function(){try{var d=document.documentElement,p=location.pathname;if(d.dataset.ui!=='canopy'||(p!=='/'&&p!=='/chat'))return;var ids=${JSON.stringify(SCENES.map((x) => x.id))},pref={index:0,anchor:0,auto:true};try{var r=JSON.parse(localStorage.getItem('levy-canopy-scenery')||'null');if(r&&typeof r.index==='number'&&typeof r.anchor==='number'){pref={index:r.index,anchor:r.anchor,auto:r.auto!==false}}}catch(e){}var n=ids.length,passed=pref.auto?Math.max(0,Math.floor((Date.now()-pref.anchor)/3600000)):0,i=(((pref.index+passed)%n)+n)%n,id=ids[i],base=${JSON.stringify(PHOTO_BASE)},set=${JSON.stringify([...PHOTO_WIDTHS])}.map(function(w){return base+'/'+id+'-'+w+'.webp '+w+'w'}).join(', '),l=document.createElement('link');l.rel='preload';l.as='image';l.setAttribute('imagesrcset',set);l.setAttribute('imagesizes',${JSON.stringify(PHOTO_SIZES)});l.setAttribute('fetchpriority','high');document.head.appendChild(l)}catch(e){}})();`
