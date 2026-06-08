---
name: Precision Technical Interface
colors:
  surface: '#051424'
  surface-dim: '#051424'
  surface-bright: '#2c3a4c'
  surface-container-lowest: '#010f1f'
  surface-container-low: '#0d1c2d'
  surface-container: '#122131'
  surface-container-high: '#1c2b3c'
  surface-container-highest: '#273647'
  on-surface: '#d4e4fa'
  on-surface-variant: '#c2c6d6'
  inverse-surface: '#d4e4fa'
  inverse-on-surface: '#233143'
  outline: '#8c909f'
  outline-variant: '#424754'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e6a'
  primary-container: '#4d8eff'
  on-primary-container: '#00285d'
  inverse-primary: '#005ac2'
  secondary: '#c0c1ff'
  on-secondary: '#1000a9'
  secondary-container: '#3131c0'
  on-secondary-container: '#b0b2ff'
  tertiary: '#ffb786'
  on-tertiary: '#502400'
  tertiary-container: '#df7412'
  on-tertiary-container: '#461f00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#e1e0ff'
  secondary-fixed-dim: '#c0c1ff'
  on-secondary-fixed: '#07006c'
  on-secondary-fixed-variant: '#2f2ebe'
  tertiary-fixed: '#ffdcc6'
  tertiary-fixed-dim: '#ffb786'
  on-tertiary-fixed: '#311400'
  on-tertiary-fixed-variant: '#723600'
  background: '#051424'
  on-background: '#d4e4fa'
  surface-variant: '#273647'
typography:
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  data-value:
    fontFamily: Geist
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  gutter-md: 16px
  margin-lg: 24px
  card-padding: 20px
  stack-gap: 12px
---

## Brand & Style

The design system is engineered for high-density enterprise environments where data clarity and system monitoring are paramount. The brand personality is **technical, precise, and authoritative**, moving away from generic corporate aesthetics toward a developer-centric, high-performance "Command Center" feel. 

The visual style is a hybrid of **Corporate Modern** and **Minimalism**, utilizing tonal layering rather than excessive borders to define hierarchy. It focuses on reducing cognitive load by prioritizing information density without sacrificing legibility. The emotional response should be one of total control, reliability, and modern efficiency.

## Colors

This design system utilizes a deep, multi-layered dark palette to ensure long-term comfort for users. The core background is a rich charcoal-black, while surfaces use a slightly lighter navy-gray to create depth.

- **Primary Blue:** A high-vibrancy "Electric Blue" used for primary actions, active states, and critical paths.
- **Surface Tiers:** Three distinct levels of dark grays are used to stack cards and containers, moving from darkest (background) to lightest (interactive elements).
- **Semantic Palette:** Strict adherence to functional colors—Success (Emerald), Warning (Amber), and Error (Rose)—ensuring alerts stand out against the dark UI.
- **Text Contrast:** Primary text is off-white (#F8FAFC) for maximum readability, while secondary labels use a muted steel gray to maintain visual hierarchy.

## Typography

The typography strategy leverages **Geist** for its exceptional legibility in technical interfaces and **JetBrains Mono** for specialized data labels and system values.

- **Scale:** A compact scale is used to accommodate dense information dashboards. 
- **Hierarchal Contrast:** High-contrast weights distinguish between "Metadata Labels" (small, muted, monospaced) and "Data Values" (standard size, bright, sans-serif).
- **Anti-Aliasing:** Specific attention is paid to rendering on dark backgrounds; weights are slightly adjusted to prevent "glowing" or blurring on low-resolution displays.

## Layout & Spacing

The design system employs a **12-column fluid grid** with fixed sidebars. The layout rhythm is based on a **4px base unit**, ensuring mathematical consistency across all margins and paddings.

- **Content Grouping:** Main content is organized into "Section Containers" which house individual cards. 
- **The "Breathable" Grid:** While the information is dense, margins between major sections (24px) provide necessary visual breaks.
- **Card Interior:** Standard cards use 20px internal padding, while nested sub-cards or data-grids use a tighter 12px padding to indicate encapsulation.
- **Mobile Reflow:** On smaller screens, the side-by-side card layout collapses into a single-column vertical stack with the sidebar transforming into a bottom-drawer or hamburger menu.

## Elevation & Depth

Hierarchy is established through **Tonal Layering** rather than heavy shadows, creating a sophisticated, flat aesthetic that feels integrated.

- **Level 0 (Background):** The darkest layer, representing the floor of the application.
- **Level 1 (Section Containers):** Subtly lighter than the background, used to group related cards.
- **Level 2 (Cards):** The primary surface for information. These feature a very subtle 1px border (#FFFFFF with 5% opacity) to define edges against the background.
- **Floating Elements:** Modals and dropdowns use a "Soft Ambient Shadow"—a deep, large-radius blur with a slight primary-color tint (#000000 at 60% and #3B82F6 at 10% opacity) to simulate physical lift.

## Shapes

The shape language is consistently **Rounded (0.5rem base)**. This provides a modern, high-end software feel that softens the "brutalist" nature of dark-mode technical data.

- **Standard Elements:** Buttons, input fields, and small cards use the base 8px (0.5rem) radius.
- **Outer Containers:** Large dashboard sections use `rounded-xl` (1.5rem) to create a distinct frame for content.
- **Status Pills:** Badges and tags are fully pill-shaped (rounded-full) to distinguish them from interactive buttons.

## Components

- **Cards:** Use a consistent header structure with an icon, title, and optional "Action" area. Cards should have a subtle 1px stroke to ensure separation on varied monitor calibrations.
- **Action Buttons:** 
    - *Primary:* Filled blue with a soft outer glow in the same color.
    - *Secondary/Ghost:* Transparent with a subtle border, turning solid on hover.
- **Data Rows:** Use a clear "Key: Value" vertical stack. The key is in `label-sm` (muted) and the value in `body-md` (high contrast).
- **Status Indicators:** Use small, high-chroma dots accompanied by text. Ensure the colors have enough contrast against the dark surface for accessibility (WCAG AA).
- **Navigation Sidebar:** Uses active-state indicators consisting of a 3px vertical "pill" on the left edge and a subtle background highlight for the entire row.
- **Input Fields:** Darker than the card surface to create an "inset" feel, with a 2px blue border only appearing on focus.