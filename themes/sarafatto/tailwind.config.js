import { addDynamicIconSelectors } from '@iconify/tailwind';

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./*.php', './inc/**/*.php', './template-parts/**/*.php', './assets/src/js/**/*.js'],
  theme: {
    colors: {
      white: 'var(--wp--preset--color--white)',
      ink: 'var(--wp--preset--color--ink)',
      brand: 'var(--wp--preset--color--brand)',
      pink: 'var(--wp--preset--color--pink)',
      yellow: 'var(--wp--preset--color--yellow)',
      muted: 'var(--wp--preset--color--muted)',
      transparent: 'transparent',
      current: 'currentColor',
    },
    spacing: {
      1: 'var(--wp--preset--spacing--1)', 2: 'var(--wp--preset--spacing--2)',
      3: 'var(--wp--preset--spacing--3)', 4: 'var(--wp--preset--spacing--4)',
      6: 'var(--wp--preset--spacing--6)', 8: 'var(--wp--preset--spacing--8)',
      12: 'var(--wp--preset--spacing--12)', 16: 'var(--wp--preset--spacing--16)',
      24: 'var(--wp--preset--spacing--24)', 32: 'var(--wp--preset--spacing--32)',
    },
    maxWidth: {
      content: 'var(--wp--style--global--content-size)',
      wide: 'var(--wp--style--global--wide-size)',
    },
    extend: {
      fontFamily: {
        body: ['var(--wp--preset--font-family--manrope)'],
        display: ['var(--wp--preset--font-family--fraunces)'],
      },
      fontSize: {
        'display-xl': 'var(--wp--preset--font-size--display-xl)',
        'display-lg': 'var(--wp--preset--font-size--display-lg)',
        h1: 'var(--wp--preset--font-size--h1)',
        h2: 'var(--wp--preset--font-size--h2)',
        h3: 'var(--wp--preset--font-size--h3)',
        'body-lg': 'var(--wp--preset--font-size--body-lg)',
        body: 'var(--wp--preset--font-size--body)',
        small: 'var(--wp--preset--font-size--small)',
        eyebrow: 'var(--wp--preset--font-size--eyebrow)',
        caption: 'var(--wp--preset--font-size--caption)',
      },
      borderRadius: { small: 'var(--radius-small)', medium: 'var(--radius-medium)', pill: 'var(--radius-pill)' },
      transitionDuration: { fast: 'var(--duration-fast)', normal: 'var(--duration-normal)', slow: 'var(--duration-slow)', menu: 'var(--duration-menu)' },
      transitionTimingFunction: { standard: 'var(--easing-standard)', soft: 'var(--easing-soft)', menu: 'var(--easing-menu)' },
      zIndex: { header: 'var(--z-header)', overlay: 'var(--z-overlay)' },
    },
  },
  plugins: [addDynamicIconSelectors()],
};
