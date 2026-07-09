# Levy Legal AI — Chat Theme Design System

> 3 Production-Ready UI Themes for a Legal AI Chat Platform
> Research-backed by analysis of Claude AI, OpenAI ChatGPT, T3 Chat, Harvey AI, and 21st.dev components
> Date: 2026-03-30

---

## Table of Contents

1. [Research Synthesis](#research-synthesis)
2. [Shared Architecture](#shared-architecture)
3. [Theme 1: SOVEREIGN — Dark Luxury Legal](#theme-1-sovereign)
4. [Theme 2: PARCHMENT — Warm Editorial Legal](#theme-2-parchment)
5. [Theme 3: NEXUS — Ultra-Modern Minimal](#theme-3-nexus)
6. [Mobile-First Responsive Strategy](#mobile-first-responsive-strategy)
7. [Folder & Document Management System](#folder--document-management-system)
8. [Component Mapping](#component-mapping)
9. [LordIcon Integration](#lordicon-integration)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Research Synthesis

### Design Philosophy Influences

| Source | Key Takeaway for Levy |
|--------|----------------------|
| **Claude AI** | Warm cream backgrounds, serif typography signals trust & literary quality. Projects system for grouping conversations + docs. Artifacts panel for side-by-side content. |
| **OpenAI ChatGPT** | Floating overlay sidebar (doesn't push content). Canvas for in-place document editing. Connector ecosystem for external files. Model mode switching (Auto/Fast/Thinking). |
| **T3 Chat** | Conversation branching (fork timelines). Local-first architecture. Hotkey-driven power-user workflows. Speed as a feature (2x ChatGPT). Multi-model unified interface. |
| **Harvey AI** | Legal-domain-specific design. Merged drafting + chat in single threads. Intent-based design tokens (`hy-` prefix). Transparent AI reasoning with citation trails. Automatic redlining. In-app draft editor. |
| **Industry Trends** | Dark mode preferred by 82% for extended sessions. Glassmorphism 2.0 with frosted panels. Streaming text reduces perceived wait by 55-70%. Bottom tab bar (3-4 items) dominates mobile. Swipe drawer replacing hamburger. |

### Key Design Principles for Levy

1. **Trust-First** — Lawyers need to trust the tool. Visual precision, citation transparency, and professional polish are non-negotiable
2. **Case-Centric Organization** — Every conversation, document, and analysis belongs to a case. Cases are the primary organizational unit (inspired by Harvey + ChatGPT Projects)
3. **Document-Native** — Ingested documents must be visible, referenced, and navigable within conversations (RAG citation panels)
4. **Mobile-Optimized** — Lawyers work from courtrooms, client meetings, and commutes. Mobile must be a first-class experience, not a responsive afterthought
5. **No Glow Effects** — Explicit design constraint. Premium quality through typography, spacing, and subtle shadows instead
6. **Zambian Identity** — Emerald green (#198754) as cultural anchor across all themes
7. **LordIcon Animated Icons** — Hover-triggered on desktop, click/viewport-triggered on mobile

---

## Shared Architecture

### Layout Structure (All Themes)

```
DESKTOP (>1024px):
+-------------------+----------------------------------------+
|                   |                                        |
|    SIDEBAR        |           MAIN CHAT AREA               |
|    (280px)        |                                        |
|                   |    [Header: Case Name + Actions]       |
|  [Logo]           |                                        |
|  [New Chat]       |    [Message Thread]                    |
|  [Search]         |      - User message (bubble)           |
|  [Cases/Folders]  |      - AI response (flat)              |
|    > Case 1       |      - Citations (collapsible)         |
|      - Chat A     |      - Document refs (inline)          |
|      - Chat B     |                                        |
|      - Docs       |    [Context Panel] (optional right)    |
|    > Case 2       |      - Active documents                |
|  [Documents]      |      - Referenced sources              |
|  [Settings]       |                                        |
|  [Profile]        |    [Chat Input Bar]                    |
|                   |      [Attach] [Input] [Send]           |
+-------------------+----------------------------------------+

MOBILE (<768px):
+----------------------------------------+
|  [Menu] [Case Name]        [Actions]   |  <- Sticky header
|                                        |
|  [Message Thread]                      |
|    - Scrollable, full width            |
|    - Cards stack vertically            |
|    - Citations collapse to chips       |
|                                        |
|  [Chat Input Bar]                      |  <- Sticky bottom
|    [+] [Input] [Send]                  |
|                                        |
+----------------------------------------+
|  [Chat] [Cases] [Docs] [Profile]       |  <- Bottom tab bar
+----------------------------------------+

MOBILE SIDEBAR (swipe from left):
+------------------+---------------------+
|                  |                     |
|  FULL-SCREEN     |  (dimmed overlay)   |
|  DRAWER          |                     |
|                  |                     |
|  [Search]        |                     |
|  [Recent Chats]  |                     |
|  [Cases]         |                     |
|  [Folders]       |                     |
|                  |                     |
+------------------+---------------------+
```

### Shared CSS Variables Structure

All three themes use the same variable names but different values. This enables instant theme switching.

```css
:root {
  /* Core */
  --background: ;
  --foreground: ;
  --card: ;
  --card-foreground: ;
  --popover: ;
  --popover-foreground: ;

  /* Brand */
  --primary: ;           /* Main action color */
  --primary-foreground: ;
  --secondary: ;         /* Supporting color */
  --secondary-foreground: ;
  --accent: ;            /* Highlight/hover */
  --accent-foreground: ;

  /* Feedback */
  --destructive: ;
  --destructive-foreground: ;
  --muted: ;
  --muted-foreground: ;

  /* Layout */
  --border: ;
  --input: ;
  --ring: ;
  --radius: ;

  /* Sidebar */
  --sidebar: ;
  --sidebar-foreground: ;
  --sidebar-primary: ;
  --sidebar-primary-foreground: ;
  --sidebar-accent: ;
  --sidebar-accent-foreground: ;
  --sidebar-border: ;
  --sidebar-ring: ;

  /* Levy-Specific (Custom) */
  --levy-emerald: ;          /* Zambian identity */
  --levy-emerald-muted: ;
  --levy-citation: ;         /* Citation highlight */
  --levy-citation-bg: ;
  --levy-document: ;         /* Document reference */
  --levy-document-bg: ;
  --levy-user-bubble: ;      /* User message */
  --levy-user-bubble-fg: ;
  --levy-ai-response: ;      /* AI response area */
  --levy-ai-response-fg: ;
  --levy-confidence-high: ;  /* Similarity tiers */
  --levy-confidence-med: ;
  --levy-confidence-low: ;
  --levy-folder-icon: ;      /* Folder system */
  --levy-active-case: ;      /* Active case highlight */

  /* Typography */
  --font-heading: ;
  --font-body: ;
  --font-mono: ;
  --font-legal: ;            /* For legal document display */

  /* Shadows (NO glow effects) */
  --shadow-card: ;
  --shadow-card-hover: ;
  --shadow-elevated: ;
  --shadow-input-focus: ;
}
```

---

## Theme 1: SOVEREIGN

### Philosophy
**"The counsel chamber after hours"**

Inspired by Harvey AI's domain-specific precision and the dark luxury of high-end legal firms. This theme channels the gravitas of mahogany-paneled law offices into a digital interface. Dark surfaces with warm gold and emerald accents create an atmosphere of authority and trust. The design says: *"This tool commands respect."*

**Design DNA**: Harvey AI (domain precision) + Caffeine theme (warm darks) + Solar Dust (amber accents)

### Color System

```css
/* SOVEREIGN — Light Mode */
:root[data-theme="sovereign"] {
  --background: #FDFBF7;        /* Warm ivory */
  --foreground: #1A1814;         /* Near-black warm */
  --card: #F8F4EE;               /* Parchment card */
  --card-foreground: #1A1814;
  --popover: #FFFFFF;
  --popover-foreground: #1A1814;

  --primary: #8B6914;            /* Antique gold */
  --primary-foreground: #FFFFFF;
  --secondary: #F1E9DA;          /* Warm linen */
  --secondary-foreground: #4A3B2E;
  --accent: #E8DCC8;             /* Warm sand */
  --accent-foreground: #3D2E1F;

  --destructive: #991B1B;        /* Deep red */
  --destructive-foreground: #FFFFFF;
  --muted: #F1E9DA;
  --muted-foreground: #78716C;

  --border: #E4D9BC;
  --input: #E4D9BC;
  --ring: #8B6914;
  --radius: 0.5rem;

  --sidebar: #F1E9DA;
  --sidebar-foreground: #4A3B2E;
  --sidebar-primary: #8B6914;
  --sidebar-primary-foreground: #FFFFFF;
  --sidebar-accent: #E8DCC8;
  --sidebar-accent-foreground: #3D2E1F;
  --sidebar-border: #DED4B8;
  --sidebar-ring: #8B6914;

  /* Levy Custom */
  --levy-emerald: #198754;
  --levy-emerald-muted: #d1fae5;
  --levy-citation: #8B6914;
  --levy-citation-bg: #FEF9E7;
  --levy-document: #6B5B3E;
  --levy-document-bg: #F8F0DD;
  --levy-user-bubble: #198754;
  --levy-user-bubble-fg: #FFFFFF;
  --levy-ai-response: transparent;
  --levy-ai-response-fg: #1A1814;
  --levy-confidence-high: #198754;
  --levy-confidence-med: #B45309;
  --levy-confidence-low: #78716C;
  --levy-folder-icon: #8B6914;
  --levy-active-case: #FEF3C7;

  --font-heading: 'Playfair Display', 'Georgia', serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-legal: 'Lora', 'Georgia', serif;

  --shadow-card: 0 1px 3px rgba(74, 59, 46, 0.06);
  --shadow-card-hover: 0 4px 12px rgba(74, 59, 46, 0.1);
  --shadow-elevated: 0 8px 24px rgba(74, 59, 46, 0.12);
  --shadow-input-focus: 0 0 0 2px rgba(139, 105, 20, 0.2);
}

/* SOVEREIGN — Dark Mode */
.dark[data-theme="sovereign"],
[data-theme="sovereign"] .dark {
  --background: #0F0D0A;        /* Rich near-black */
  --foreground: #E8E0D0;         /* Warm cream text */
  --card: #1A1714;               /* Dark mahogany */
  --card-foreground: #E8E0D0;
  --popover: #1E1B16;
  --popover-foreground: #E8E0D0;

  --primary: #D4A843;            /* Bright gold */
  --primary-foreground: #0F0D0A;
  --secondary: #2A2520;          /* Dark warm */
  --secondary-foreground: #C8BCA8;
  --accent: #332D25;             /* Warm dark accent */
  --accent-foreground: #E8DCC8;

  --destructive: #DC2626;
  --destructive-foreground: #FFFFFF;
  --muted: #1E1B16;
  --muted-foreground: #9C9488;

  --border: #332D25;
  --input: #332D25;
  --ring: #D4A843;

  --sidebar: #141210;
  --sidebar-foreground: #C8BCA8;
  --sidebar-primary: #D4A843;
  --sidebar-primary-foreground: #0F0D0A;
  --sidebar-accent: #1E1B16;
  --sidebar-accent-foreground: #E8DCC8;
  --sidebar-border: #2A2520;
  --sidebar-ring: #D4A843;

  --levy-emerald: #22c55e;
  --levy-emerald-muted: #14532d;
  --levy-citation: #D4A843;
  --levy-citation-bg: #2A2210;
  --levy-document: #B8A070;
  --levy-document-bg: #1E1A12;
  --levy-user-bubble: #166534;
  --levy-user-bubble-fg: #FFFFFF;
  --levy-ai-response: transparent;
  --levy-ai-response-fg: #E8E0D0;
  --levy-confidence-high: #22c55e;
  --levy-confidence-med: #F97316;
  --levy-confidence-low: #9C9488;
  --levy-folder-icon: #D4A843;
  --levy-active-case: #2A2210;

  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.3);
  --shadow-card-hover: 0 4px 12px rgba(0, 0, 0, 0.4);
  --shadow-elevated: 0 8px 24px rgba(0, 0, 0, 0.5);
  --shadow-input-focus: 0 0 0 2px rgba(212, 168, 67, 0.3);
}
```

### Visual Identity

- **Heading Font**: Playfair Display (serif) — Conveys legal authority, refinement
- **Body Font**: Inter — Clean readability for long legal texts
- **Legal Document Font**: Lora — Elegant serif for displaying ingested legal documents
- **Mono Font**: JetBrains Mono — For code blocks, section references
- **Border Radius**: 0.5rem — Slightly rounded, professional
- **Key Visual**: Thin gold rule lines separating sections. Subtle warm grain texture on card backgrounds (CSS noise filter at 2% opacity)
- **Icons**: LordIcon in gold (#8B6914 light / #D4A843 dark) with `trigger="hover"` on desktop
- **User Messages**: Emerald bubble with thought-bubble tail animation (existing pattern)
- **AI Responses**: Clean left-aligned text, no bubble, gold accent on citation chips
- **Empty State**: Scales of justice icon (LordIcon animated), gold gradient text

### Desktop Layout Specifics

- Sidebar: 280px, warm linen background, gold active indicator (3px left border)
- Case folders: Accordion with gold chevron, case count badge
- Chat area: Max-width 768px centered, generous vertical spacing (24px between messages)
- Input bar: Glassmorphic with warm backdrop-filter, gold ring on focus
- Context panel (optional): 320px right panel for active document viewer

### Mobile Specifics

- Bottom tab bar: 4 items (Chat, Cases, Documents, Profile) with LordIcon animated icons
- Swipe-left from edge opens full-screen drawer with case/folder tree
- Chat input: Fixed bottom with attach (+) button opening bottom sheet
- Citations: Collapse to gold chips that expand on tap
- Cards: Full-width with 16px horizontal padding, stacked vertically
- Document previews: Bottom sheet with swipe-to-dismiss

---

## Theme 2: PARCHMENT

### Philosophy
**"The modern law library"**

Inspired by Claude AI's warm, literary aesthetic and the editorial quality of premium legal publications. This theme treats legal AI as a scholarly companion — warm cream surfaces, thoughtful serif typography, and earthy terra cotta accents create a space that feels like the best law library you've ever worked in. The design says: *"This tool thinks deeply."*

**Design DNA**: Claude AI (warm serif) + 21st.dev first theme (terra cotta) + Cosmic Night (clean structure)

### Color System

```css
/* PARCHMENT — Light Mode */
:root[data-theme="parchment"] {
  --background: #FAF8F3;        /* Warm paper */
  --foreground: #3D3929;         /* Dark olive (Claude-inspired) */
  --card: #FFFFFF;               /* Clean white cards */
  --card-foreground: #3D3929;
  --popover: #FFFFFF;
  --popover-foreground: #3D3929;

  --primary: #C96442;            /* Terra cotta */
  --primary-foreground: #FFFFFF;
  --secondary: #F0EBE0;          /* Warm cream */
  --secondary-foreground: #535146;
  --accent: #E9E4D8;             /* Light parchment */
  --accent-foreground: #28261B;

  --destructive: #B91C1C;
  --destructive-foreground: #FFFFFF;
  --muted: #F0EBE0;
  --muted-foreground: #83827D;

  --border: #E0D9C8;
  --input: #E0D9C8;
  --ring: #C96442;
  --radius: 0.625rem;

  --sidebar: #F5F2EB;
  --sidebar-foreground: #3D3929;
  --sidebar-primary: #C96442;
  --sidebar-primary-foreground: #FFFFFF;
  --sidebar-accent: #E9E4D8;
  --sidebar-accent-foreground: #3D3929;
  --sidebar-border: #E0D9C8;
  --sidebar-ring: #C96442;

  /* Levy Custom */
  --levy-emerald: #198754;
  --levy-emerald-muted: #ECFDF5;
  --levy-citation: #9C4A2E;
  --levy-citation-bg: #FFF5F0;
  --levy-document: #8B7355;
  --levy-document-bg: #FAF5ED;
  --levy-user-bubble: #198754;
  --levy-user-bubble-fg: #FFFFFF;
  --levy-ai-response: transparent;
  --levy-ai-response-fg: #3D3929;
  --levy-confidence-high: #198754;
  --levy-confidence-med: #C96442;
  --levy-confidence-low: #83827D;
  --levy-folder-icon: #C96442;
  --levy-active-case: #FFF5F0;

  --font-heading: 'Lora', 'Georgia', serif;
  --font-body: 'Source Sans 3', 'Inter', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;
  --font-legal: 'Lora', 'Crimson Text', 'Georgia', serif;

  --shadow-card: 0 1px 2px rgba(61, 57, 41, 0.04);
  --shadow-card-hover: 0 2px 8px rgba(61, 57, 41, 0.08);
  --shadow-elevated: 0 4px 16px rgba(61, 57, 41, 0.1);
  --shadow-input-focus: 0 0 0 2px rgba(201, 100, 66, 0.15);
}

/* PARCHMENT — Dark Mode */
.dark[data-theme="parchment"],
[data-theme="parchment"] .dark {
  --background: #1C1A16;        /* Warm dark */
  --foreground: #D4CEBC;         /* Warm cream text */
  --card: #262420;               /* Dark card */
  --card-foreground: #D4CEBC;
  --popover: #2A2824;
  --popover-foreground: #D4CEBC;

  --primary: #D97757;            /* Bright terra cotta */
  --primary-foreground: #FFFFFF;
  --secondary: #332F28;
  --secondary-foreground: #C3BCA8;
  --accent: #2A2720;
  --accent-foreground: #E9E4D8;

  --destructive: #EF4444;
  --destructive-foreground: #FFFFFF;
  --muted: #262420;
  --muted-foreground: #9C9688;

  --border: #3A362E;
  --input: #3A362E;
  --ring: #D97757;

  --sidebar: #1A1816;
  --sidebar-foreground: #C3BCA8;
  --sidebar-primary: #D97757;
  --sidebar-primary-foreground: #FFFFFF;
  --sidebar-accent: #262420;
  --sidebar-accent-foreground: #D4CEBC;
  --sidebar-border: #332F28;
  --sidebar-ring: #D97757;

  --levy-emerald: #22c55e;
  --levy-emerald-muted: #14532d;
  --levy-citation: #D97757;
  --levy-citation-bg: #2A1F18;
  --levy-document: #C8A878;
  --levy-document-bg: #221E18;
  --levy-user-bubble: #166534;
  --levy-user-bubble-fg: #FFFFFF;
  --levy-ai-response: transparent;
  --levy-ai-response-fg: #D4CEBC;
  --levy-confidence-high: #22c55e;
  --levy-confidence-med: #D97757;
  --levy-confidence-low: #9C9688;
  --levy-folder-icon: #D97757;
  --levy-active-case: #2A1F18;

  --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.2);
  --shadow-card-hover: 0 4px 12px rgba(0, 0, 0, 0.3);
  --shadow-elevated: 0 8px 24px rgba(0, 0, 0, 0.35);
  --shadow-input-focus: 0 0 0 2px rgba(217, 119, 87, 0.25);
}
```

### Visual Identity

- **Heading Font**: Lora (serif) — Warm, scholarly, inviting
- **Body Font**: Source Sans 3 — Highly readable, slightly warmer than Inter
- **Legal Document Font**: Lora / Crimson Text — Classical legal document feel
- **Mono Font**: IBM Plex Mono — Warm monospace for section references
- **Border Radius**: 0.625rem — Slightly more rounded than Sovereign, approachable
- **Key Visual**: Terra cotta accent bars on active items. Subtle paper texture at 1% opacity on background. Bookmarks/ribbons as folder indicators
- **Icons**: LordIcon in terra cotta (#C96442 light / #D97757 dark)
- **User Messages**: Emerald bubble with Claude-style generous spacing
- **AI Responses**: Serif body text (Lora) for legal analysis, creating a "reading" experience. Sans-serif for UI elements
- **Empty State**: Open book icon (LordIcon animated), warm gradient text "What legal matter can I help you with?"
- **Unique Element**: AI responses use serif font for legal content — this mirrors Claude's literary approach and signals thoughtfulness. When AI cites a law, the citation appears as an inline chip with a terra cotta left border

### Desktop Layout Specifics

- Sidebar: 280px, subtle warm tint, terra cotta dot indicator on active items
- Case folders: Tree view with book/folder icons, expandable with smooth animation
- Chat area: Max-width 720px centered (slightly narrower for reading comfort), 28px message spacing
- Input bar: Clean border bottom, terra cotta ring on focus, subtle shadow
- Citation display: Expandable inline cards with act name, section, and similarity badge

### Mobile Specifics

- Bottom tab bar: 4 items with warm terra cotta active indicator (filled dot below icon)
- Swipe drawer: Warm cream overlay with case tree
- Chat input: Clean bottom bar, terra cotta send button
- AI responses: Full-width serif text, readable like a book page
- Document cards: Rounded cards with book icon, warm shadows
- Pull-to-refresh: Terra cotta spinner

---

## Theme 3: NEXUS

### Philosophy
**"The command center for modern law"**

Inspired by T3 Chat's speed-first developer aesthetic, OpenAI's Canvas workspace, and the stark minimalism of Vercel/Linear. This theme is for the tech-forward lawyer who wants power, speed, and zero visual noise. Pure black and white with electric emerald accents. The design says: *"This tool is fast and precise."*

**Design DNA**: T3 Chat (speed-first) + Mono theme (0 radius, monospace) + OpenAI (floating sidebar) + Linear (command palette UX)

### Color System

```css
/* NEXUS — Light Mode */
:root[data-theme="nexus"] {
  --background: #FFFFFF;        /* Pure white */
  --foreground: #0A0A0A;         /* Pure black */
  --card: #FAFAFA;               /* Near-white */
  --card-foreground: #0A0A0A;
  --popover: #FFFFFF;
  --popover-foreground: #0A0A0A;

  --primary: #0A0A0A;            /* Black primary */
  --primary-foreground: #FAFAFA;
  --secondary: #F5F5F5;          /* Light gray */
  --secondary-foreground: #171717;
  --accent: #F0F0F0;
  --accent-foreground: #171717;

  --destructive: #E7000B;
  --destructive-foreground: #FFFFFF;
  --muted: #F5F5F5;
  --muted-foreground: #737373;

  --border: #E5E5E5;
  --input: #E5E5E5;
  --ring: #198754;               /* Emerald ring — the only color */
  --radius: 0.375rem;            /* Tight, sharp */

  --sidebar: #FAFAFA;
  --sidebar-foreground: #0A0A0A;
  --sidebar-primary: #0A0A0A;
  --sidebar-primary-foreground: #FAFAFA;
  --sidebar-accent: #F0F0F0;
  --sidebar-accent-foreground: #171717;
  --sidebar-border: #E5E5E5;
  --sidebar-ring: #198754;

  /* Levy Custom */
  --levy-emerald: #198754;
  --levy-emerald-muted: #ECFDF5;
  --levy-citation: #198754;
  --levy-citation-bg: #F0FDF4;
  --levy-document: #525252;
  --levy-document-bg: #F5F5F5;
  --levy-user-bubble: #0A0A0A;
  --levy-user-bubble-fg: #FAFAFA;
  --levy-ai-response: transparent;
  --levy-ai-response-fg: #0A0A0A;
  --levy-confidence-high: #198754;
  --levy-confidence-med: #737373;
  --levy-confidence-low: #A3A3A3;
  --levy-folder-icon: #525252;
  --levy-active-case: #F0FDF4;

  --font-heading: 'Inter', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'Geist Mono', 'JetBrains Mono', monospace;
  --font-legal: 'Inter', system-ui, sans-serif;

  --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.03);
  --shadow-card-hover: 0 2px 8px rgba(0, 0, 0, 0.06);
  --shadow-elevated: 0 4px 16px rgba(0, 0, 0, 0.08);
  --shadow-input-focus: 0 0 0 2px rgba(25, 135, 84, 0.2);
}

/* NEXUS — Dark Mode */
.dark[data-theme="nexus"],
[data-theme="nexus"] .dark {
  --background: #09090B;        /* True dark */
  --foreground: #FAFAFA;
  --card: #18181B;               /* Zinc-900 */
  --card-foreground: #FAFAFA;
  --popover: #18181B;
  --popover-foreground: #FAFAFA;

  --primary: #FAFAFA;            /* White primary */
  --primary-foreground: #09090B;
  --secondary: #27272A;          /* Zinc-800 */
  --secondary-foreground: #FAFAFA;
  --accent: #27272A;
  --accent-foreground: #FAFAFA;

  --destructive: #EF4444;
  --destructive-foreground: #FFFFFF;
  --muted: #27272A;
  --muted-foreground: #A1A1AA;

  --border: #27272A;
  --input: #27272A;
  --ring: #22c55e;               /* Bright emerald */

  --sidebar: #09090B;
  --sidebar-foreground: #FAFAFA;
  --sidebar-primary: #FAFAFA;
  --sidebar-primary-foreground: #09090B;
  --sidebar-accent: #18181B;
  --sidebar-accent-foreground: #FAFAFA;
  --sidebar-border: #27272A;
  --sidebar-ring: #22c55e;

  --levy-emerald: #22c55e;
  --levy-emerald-muted: #14532d;
  --levy-citation: #22c55e;
  --levy-citation-bg: #0A1F0F;
  --levy-document: #A1A1AA;
  --levy-document-bg: #18181B;
  --levy-user-bubble: #27272A;
  --levy-user-bubble-fg: #FAFAFA;
  --levy-ai-response: transparent;
  --levy-ai-response-fg: #FAFAFA;
  --levy-confidence-high: #22c55e;
  --levy-confidence-med: #A1A1AA;
  --levy-confidence-low: #52525B;
  --levy-folder-icon: #A1A1AA;
  --levy-active-case: #0A1F0F;

  --shadow-card: 0 1px 2px rgba(0, 0, 0, 0.4);
  --shadow-card-hover: 0 2px 8px rgba(0, 0, 0, 0.5);
  --shadow-elevated: 0 4px 16px rgba(0, 0, 0, 0.6);
  --shadow-input-focus: 0 0 0 2px rgba(34, 197, 94, 0.3);
}
```

### Visual Identity

- **All Fonts**: Inter (headings + body) + Geist Mono (code/references) — Zero serif. Pure utility
- **Border Radius**: 0.375rem — Tight, almost sharp. No soft curves
- **Key Visual**: Monochrome everything. Emerald green is the ONLY color and appears exclusively for: active states, success indicators, the Zambian identity, and focus rings. Everything else is black/white/gray
- **Icons**: LordIcon in black (#0A0A0A light / #FAFAFA dark), emerald only when active
- **User Messages**: Black bubble (light mode) / dark zinc bubble (dark mode), no thought-bubble animation
- **AI Responses**: Clean, flat, monospaced section references. Data-dense with tight line-height
- **Empty State**: Minimal — just the Levy logo mark and "Start a conversation" in muted text
- **Unique Element**: Command palette (Cmd+K) as the primary navigation method. Keyboard shortcuts for everything. Conversation branching like T3 Chat. Floating sidebar overlay (ChatGPT-style) instead of push sidebar

### Desktop Layout Specifics

- Sidebar: Floating overlay (triggered by hover on left edge or Cmd+B), 300px, doesn't push content
- Case list: Flat list, no tree view, filterable by tags. Monospaced case numbers
- Chat area: Max-width 800px centered, tight 16px message spacing, dense information layout
- Input bar: Minimal border, emerald ring on focus, keyboard shortcut hints
- Command palette: Cmd+K opens full search across cases, documents, chats, actions
- Keyboard shortcuts: Cmd+N (new chat), Cmd+U (upload), Cmd+/ (shortcuts panel)

### Mobile Specifics

- Bottom tab bar: 3 items only (Chat, Cases, More) — ultra-minimal
- No swipe drawer — use "More" tab for full navigation
- Chat input: Minimal, dark, emerald send button
- Messages: Full-width, tight spacing, monospaced references
- Document list: Flat table view, sortable columns
- No animations on mobile — pure speed, zero jank

---

## Mobile-First Responsive Strategy

### Breakpoints

```css
/* Mobile first — these are min-width breakpoints */
/* Default: 0-639px (Mobile phones) */
/* sm: 640px+ (Large phones, small tablets) */
/* md: 768px+ (Tablets) */
/* lg: 1024px+ (Small desktops) */
/* xl: 1280px+ (Desktops) */
/* 2xl: 1536px+ (Large desktops) */
```

### Mobile Layout Rules

1. **Sidebar**: Hidden by default. Accessible via:
   - Hamburger icon in header (all themes)
   - Swipe from left edge (Sovereign, Parchment)
   - "More" tab in bottom nav (Nexus)

2. **Bottom Tab Bar**: Fixed, 56px height, 4 items max
   ```
   [Chat]  [Cases]  [Documents]  [Profile]
   ```
   Each tab uses a LordIcon with `trigger="click"` (no hover on mobile)

3. **Chat Input**: Fixed bottom, above tab bar
   - Minimum height: 48px (touch target)
   - Auto-expand up to 50% viewport height
   - Attach button opens bottom sheet with options:
     - Camera (scan document)
     - Photo Library
     - Files (PDF, DOCX)
     - Paste from clipboard
   - Send button: 44x44px minimum touch target

4. **Message Cards**: Full width (minus 16px padding each side)
   - User messages: Right-aligned bubble, max-width 85%
   - AI responses: Left-aligned, full width, no bubble
   - Citations: Collapsed to single-line chip, tap to expand in bottom sheet
   - Document references: Horizontal scroll strip of document chips

5. **Case/Folder Navigation** (mobile):
   - Full-screen view when navigating cases
   - Breadcrumb trail at top: Home > Case Name > Chat
   - Back button (left arrow) in header
   - Long-press on case for context menu (rename, archive, share)

6. **Document Viewer** (mobile):
   - Full-screen bottom sheet (95% height)
   - Swipe down to dismiss
   - Pinch-to-zoom on document content
   - Floating "Ask about this" button

7. **Search**:
   - Full-screen search overlay on mobile
   - Recent searches, suggested queries
   - Filter chips (Cases, Documents, Chats)

### Touch Targets

All interactive elements must meet minimum 44x44px touch targets per Apple HIG. Spacing between touch targets: minimum 8px.

### Performance on Mobile

- Lazy load conversation history (load 20 messages, infinite scroll up)
- Skeleton loading for message cards
- Image thumbnails: 150px max-width, tap to full-screen
- Reduce animations on `prefers-reduced-motion`
- Use `content-visibility: auto` for off-screen message cards

---

## Folder & Document Management System

### Architecture: Case-Centric Organization

Inspired by Harvey AI's unified experience and ChatGPT Projects:

```
WORKSPACE (Levy account)
  |
  +-- CASES (primary organizational unit)
  |     |
  |     +-- Case: "Smith v. Republic"
  |     |     |
  |     |     +-- Chat Sessions
  |     |     |     +-- "Initial Analysis" (chat)
  |     |     |     +-- "Contract Review" (chat with 3 docs attached)
  |     |     |     +-- "Court Prep Q&A" (chat)
  |     |     |
  |     |     +-- Documents
  |     |     |     +-- "Employment Act.pdf" (ingested, 450 chunks)
  |     |     |     +-- "Contract_Draft_v2.docx" (ingested, 120 chunks)
  |     |     |     +-- "Client Notes.pdf" (pending ingestion)
  |     |     |
  |     |     +-- Case Notes (quick text notes)
  |     |     +-- Case Settings (custom AI instructions for this case)
  |     |
  |     +-- Case: "Lusaka Property Dispute"
  |           +-- ...
  |
  +-- GENERAL LIBRARY (shared across all cases)
  |     +-- "Constitution of Zambia.pdf"
  |     +-- "Employment Act 2019.pdf"
  |     +-- "Companies Act.pdf"
  |     +-- ... (11 Zambian legal acts)
  |
  +-- QUICK CHATS (no case association)
        +-- "General legal question"
        +-- "Quick statute lookup"
```

### Desktop Folder UI

```
SIDEBAR (280px)
+------------------------------+
| [Levy Logo]           [+New] |
|------------------------------|
| [Search cases & docs...]     |
|------------------------------|
| CASES                   [+]  |
|   > Smith v. Republic    (3) |  <- 3 = chat count
|     - Initial Analysis       |
|     - Contract Review        |
|     - Court Prep Q&A         |
|     [Documents]         (2)  |
|   > Lusaka Property     (1)  |
|   > Mwansa Labor Case   (5)  |
|------------------------------|
| GENERAL LIBRARY         [+]  |
|   Constitution of Zambia     |
|   Employment Act 2019        |
|   Companies Act              |
|------------------------------|
| QUICK CHATS                  |
|   Today                      |
|     Quick statute lookup     |
|   Yesterday                  |
|     General legal question   |
|------------------------------|
| [Settings]        [Profile]  |
+------------------------------+
```

### Mobile Folder UI

**Cases Tab (full screen):**
```
+----------------------------------------+
| Cases                    [+] [Search]  |
|                                        |
| +------------------------------------+ |
| | Smith v. Republic                  | |
| | 3 chats, 2 documents              | |
| | Last active: 2 hours ago          | |
| +------------------------------------+ |
|                                        |
| +------------------------------------+ |
| | Lusaka Property Dispute            | |
| | 1 chat, 4 documents               | |
| | Last active: Yesterday             | |
| +------------------------------------+ |
|                                        |
| +------------------------------------+ |
| | Mwansa Labor Case                  | |
| | 5 chats, 1 document               | |
| | Last active: Mar 28               | |
| +------------------------------------+ |
|                                        |
+----------------------------------------+
| [Chat] [Cases*] [Docs] [Profile]      |
+----------------------------------------+
```

**Case Detail (full screen):**
```
+----------------------------------------+
| [<Back] Smith v. Republic    [...]     |
|                                        |
| [Chats] [Documents] [Notes] [Settings]|
|                                        |
| CHATS                                  |
| +------------------------------------+ |
| | Initial Analysis                   | |
| | "Can you analyze the employment..."| |
| | 2 hours ago                        | |
| +------------------------------------+ |
| +------------------------------------+ |
| | Contract Review                    | |
| | 3 documents attached               | |
| | Yesterday                          | |
| +------------------------------------+ |
|                                        |
| [+ New Chat in this Case]             |
+----------------------------------------+
```

### Document Context Indicators

When a user is in a chat that has documents attached, show a context strip:

**Desktop:**
```
+--------------------------------------------+
| Context: Smith v. Republic                  |
| [Employment Act] [Contract_v2] [+ Add Doc] |
+--------------------------------------------+
| Chat messages below...                      |
```

**Mobile:**
```
+----------------------------------------+
| [<] Smith v. Republic > Contract Rev.  |
| [2 docs active] [tap to manage]       |
+----------------------------------------+
```

### Document Upload Flow (Mobile)

1. Tap [+] in chat input
2. Bottom sheet appears:
   ```
   +------------------------------------+
   |          Upload Document            |
   |                                     |
   |  [Camera/Scan]  [Photo Library]     |
   |  [Files]        [Paste Text]        |
   |                                     |
   |  Recent Documents:                  |
   |  - Contract_v2.docx (2 days ago)   |
   |  - Client_Notes.pdf (3 days ago)    |
   |                                     |
   +------------------------------------+
   ```
3. After upload, show progress card in chat:
   ```
   +------------------------------------+
   | Ingesting: Contract_v2.docx        |
   | [=========>        ] 65%           |
   | Processing 120 chunks...           |
   +------------------------------------+
   ```
4. When complete, document chip appears in context strip

---

## Component Mapping

### From Component Library (~/component-library)

| Component | Usage in Levy | Theme Adaptation |
|-----------|--------------|------------------|
| **Animated AI Input** | Main chat input bar | Customize colors per theme, add document attach |
| **Text Shimmer** | AI "thinking" state | Use theme primary color for shimmer |
| **Sidebar (Aceternity)** | Case/folder navigation | Customize width, colors, add folder tree |
| **Data Table** | Document management, case lists | Use theme borders, add status badges |
| **Command Palette (cmdk)** | Global search (Cmd+K) | Nexus theme primary nav method |
| **Animated Dropdown** | Case actions, document actions | Theme-colored stagger animation |
| **Toast (Sonner)** | Upload success, AI alerts, errors | Theme-specific variants |
| **Dialog** | New case creation, document upload | Theme border radius and colors |
| **Drawer** | Mobile sidebar, document viewer | Full-screen on mobile |
| **Status Badge** | Case status, document ingestion state | Emerald/amber/gray tiers |
| **Badge Delta** | Case activity indicators | Show new messages/updates |
| **Accordion** | Case folder expand/collapse | Gold chevron (Sovereign), terra cotta (Parchment) |
| **Avatar** | User profile, AI avatar | Theme-appropriate styling |
| **Floating Action Menu** | Mobile quick actions (new chat, upload, search) | Theme primary color |
| **Progress Indicator** | Document ingestion, multi-step workflows | 3-step with emerald progress |
| **Tooltip** | Legal term definitions on hover | Theme popover colors |
| **Spinner/Loader** | AI processing, document loading | Match theme primary |
| **Card** | Message cards, case cards, document cards | Per-theme shadow system |
| **Async Select** | Case selection, document filter, tag selection | Server-side search for large case lists |
| **Notification Card** | Case updates, AI completion alerts | Avatar + status + action |

### From 21st.dev Components (User-Provided)

| Component | Usage in Levy |
|-----------|--------------|
| **ShiningText** | AI "thinking..." indicator, streaming state |
| **AI_Prompt (Animated)** | Alternative chat input with model selector |
| **PromptInputBox** | Rich input with voice, search, think, canvas modes |
| **ClaudeChatInput** | Claude-style input with file preview cards |

### Recommended: Use ClaudeChatInput as base for Parchment theme, PromptInputBox for Nexus theme, and a customized Animated AI Input for Sovereign theme.

---

## LordIcon Integration

### Icon Mapping

| UI Element | LordIcon Name | Trigger (Desktop) | Trigger (Mobile) |
|-----------|---------------|-------------------|-----------------|
| New Chat | `wjyqkzgo` (edit/compose) | hover | click |
| Cases/Folder | `jkiqllal` (folder) | hover | click |
| Documents | `zyzoeeaq` (documents) | hover | click |
| Search | `msoeawqm` (search) | hover | click |
| Upload | `jgnngzce` (upload) | hover | click |
| Settings | `hwuyodym` (settings/gear) | hover | click |
| Profile/User | `dxjqoygy` (avatar) | hover | click |
| Send Message | `ternnbni` (send/arrow) | hover | click |
| Delete | `kfzfxczd` (trash) | hover | click |
| Star/Favorite | `rjzlnunf` (star) | hover | click |
| Citation | `vfczflna` (link) | hover | in (viewport) |
| Legal Scale | `wlpxtupd` (balance) | loop-on-hover | in |
| Notification | `psnhyobz` (bell) | hover | click |
| Calendar | `abfverha` (calendar) | hover | click |
| Download | `ternnbni` (download) | hover | click |
| Archive | `jprbrwfl` (archive) | hover | click |

### Implementation Pattern

```tsx
// Desktop: hover trigger with target on parent
<div className="menu-item group">
  <lord-icon
    src="/icons/folder.json"
    trigger="hover"
    target=".menu-item"
    colors="primary:var(--levy-folder-icon)"
    style={{ width: '24px', height: '24px' }}
  />
  <span>Cases</span>
</div>

// Mobile: click trigger
<lord-icon
  src="/icons/folder.json"
  trigger="click"
  colors="primary:var(--levy-folder-icon)"
  style={{ width: '24px', height: '24px' }}
/>

// Active state: use emerald color
<lord-icon
  src="/icons/folder.json"
  trigger="loop"
  colors="primary:var(--levy-emerald)"
  style={{ width: '24px', height: '24px' }}
/>
```

### Color Filtering (from existing Levy pattern)

```css
/* Light icons on dark backgrounds */
.lordicon-light {
  filter: invert(1) brightness(0.85);
}

/* Active/selected state — emerald tint */
.lordicon-active {
  filter: invert(48%) sepia(79%) saturate(2476%)
          hue-rotate(130deg) brightness(95%) contrast(101%);
}

/* Theme-specific coloring */
[data-theme="sovereign"] .lordicon-themed {
  filter: invert(38%) sepia(98%) saturate(347%)
          hue-rotate(10deg) brightness(97%);  /* Gold */
}

[data-theme="parchment"] .lordicon-themed {
  filter: invert(45%) sepia(60%) saturate(500%)
          hue-rotate(340deg) brightness(90%);  /* Terra cotta */
}

[data-theme="nexus"] .lordicon-themed {
  /* No filter — use default black/white */
}
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
1. Create theme CSS files with all CSS variables for all 3 themes
2. Set up theme switcher using `next-themes` + `data-theme` attribute
3. Update `globals.css` to use the shared variable structure
4. Add Levy-specific custom variables to the existing system
5. Install fonts: Playfair Display, Lora, Source Sans 3, Geist Mono, IBM Plex Mono

### Phase 2: Shared Components (Week 2)
1. Update sidebar component with folder/case tree view
2. Create `CaseFolder` component (accordion-based)
3. Create `DocumentContextStrip` component (shows active docs in chat)
4. Create `CitationChip` component (theme-aware)
5. Create `MatchBadge` update for theme colors
6. Create mobile `BottomTabBar` component
7. Create `BottomSheet` component for mobile overlays

### Phase 3: Chat Interface (Week 3)
1. Update `ChatInput` to support theme variants
2. Update `ChatMessage` for theme-specific styling
3. Create `DocumentUploadProgress` component
4. Create `AIThinkingState` with ShiningText
5. Update citation display for each theme
6. Create command palette (Cmd+K) for Nexus theme

### Phase 4: Mobile Optimization (Week 4)
1. Implement bottom tab bar navigation
2. Create swipe drawer for sidebar
3. Optimize all cards for mobile stacking
4. Create mobile document upload bottom sheet
5. Create mobile case detail view
6. Test all touch targets (44x44px minimum)
7. Performance audit: lazy loading, skeleton states, content-visibility

### Phase 5: Polish (Week 5)
1. Add LordIcon animations across all touchpoints
2. Fine-tune shadows, transitions, micro-interactions
3. Cross-browser testing (Safari, Chrome, Firefox)
4. Accessibility audit (WCAG 2.1 AA)
5. Performance audit (Lighthouse score >90)
6. User testing with 2-3 legal professionals

---

## Theme Comparison Summary

| Dimension | SOVEREIGN | PARCHMENT | NEXUS |
|-----------|-----------|-----------|-------|
| **Mood** | Authoritative luxury | Scholarly warmth | Clinical precision |
| **Primary Color** | Antique gold (#8B6914) | Terra cotta (#C96442) | Emerald only (#198754) |
| **Background** | Warm ivory / rich dark | Warm paper / warm dark | Pure white / true black |
| **Typography** | Playfair Display + Inter | Lora + Source Sans | Inter only + Geist Mono |
| **Border Radius** | 0.5rem | 0.625rem | 0.375rem |
| **Sidebar** | Push, accordion folders | Push, tree view | Floating overlay |
| **AI Response Style** | Clean sans-serif | Serif body (reading mode) | Dense, monospaced refs |
| **Mobile Nav** | 4-tab + swipe drawer | 4-tab + swipe drawer | 3-tab + "More" menu |
| **Target Lawyer** | Senior partner, traditional firm | Academic, research-focused | Tech-forward, startup legal |
| **Inspired By** | Harvey + Caffeine theme | Claude + 21st terra cotta | T3 + Mono + Linear |
| **Key Differentiator** | Gold accents, grain texture | Serif AI responses, bookmarks | Cmd+K everything, zero color |

---

*Document generated from deep research analysis of Claude AI, OpenAI ChatGPT, T3 Chat, Harvey AI, 21st.dev component ecosystem, and modern AI chat design trends (2025-2026). All themes maintain Levy's core identity: Zambian emerald green, no glow effects, premium quality, Clarity-inspired foundations.*
