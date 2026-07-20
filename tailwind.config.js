/** @type {import('tailwindcss').Config} */
module.exports = {
  // All markup + the class names used by the inline JS live in this one file.
  content: ["./frontend/index.html"],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
  // Match the previous CDN behaviour: the app runs on data-theme="dark",
  // with light available too.
  daisyui: {
    themes: ["light", "dark"],
    logs: false,
  },
};
