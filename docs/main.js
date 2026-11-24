// Page behaviour: theme switch, sticky header, one orchestrated entrance,
// restrained scroll reveals, card tilt and the WebGL field. Without JS, with
// reduced motion or on Save-Data the page is complete and static.
const root = document.documentElement;
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const saveData = Boolean(navigator.connection && navigator.connection.saveData);
const gsap = window.gsap;
const ScrollTrigger = window.ScrollTrigger;
let field = null;

/* ------------------------------------------------------------ theme */
const themeBtn = document.querySelector(".theme");
function effectiveTheme() {
  const set = root.getAttribute("data-theme");
  if (set) return set;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}
function labelTheme() {
  const next = effectiveTheme() === "dark" ? "hellem" : "dunklem";
  themeBtn.setAttribute("aria-label", `Zu ${next} Farbschema wechseln`);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", effectiveTheme() === "dark" ? "#050608" : "#f4f3ee");
}
if (themeBtn) {
  labelTheme();
  themeBtn.addEventListener("click", () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch (e) {}
    labelTheme();
    if (field) field.theme();
  });
}

/* ------------------------------------------------------------ header */
const top = document.querySelector(".top");
function stick() {
  top.classList.toggle("is-stuck", window.scrollY > 24);
}
stick();
window.addEventListener("scroll", stick, { passive: true });

/* ------------------------------------------------------------ field */
const hero = document.querySelector(".hero");
function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") || c.getContext("webgl"));
  } catch (e) {
    return false;
  }
}
if (!reduce && !saveData && webglAvailable()) {
  import("./scene.js")
    .then(({ createField }) => {
      field = createField(hero.querySelector(".hero__canvas"), {
        onFirstFrame: () => hero.classList.add("is-live"),
      });
    })
    .catch(() => {
      /* keep the static CSS field */
    });
}

/* ------------------------------------------------------------ motion */
if (!reduce && gsap && ScrollTrigger) {
  gsap.registerPlugin(ScrollTrigger);
  root.classList.add("motion-ready");

  const ease = "expo.out";
  gsap.set("[data-reveal]", { y: 28 });
  gsap.set('[data-anim="hero"]', { y: 18 });

  const intro = gsap.timeline({ defaults: { ease, duration: 1.2 } });
  intro
    .to('[data-anim="top"]', { opacity: 1, duration: 1 }, 0.1)
    .to(".hero__title .line__in", { y: 0, duration: 1.4, stagger: 0.12 }, 0.15)
    .to('[data-anim="hero"]', { opacity: 1, y: 0, stagger: 0.08 }, 0.55);

  ScrollTrigger.batch("[data-reveal]", {
    start: "top 88%",
    once: true,
    onEnter: (batch) => gsap.to(batch, { opacity: 1, y: 0, duration: 1.1, ease, stagger: 0.08, overwrite: true }),
  });

  gsap.to(".progress span", {
    scaleX: 1,
    ease: "none",
    scrollTrigger: { trigger: document.body, start: "top top", end: "bottom bottom", scrub: 0.4 },
  });

  ScrollTrigger.create({
    trigger: hero,
    start: "top top",
    end: "bottom top",
    onUpdate: (self) => field && field.setScroll(self.progress),
  });
  gsap.to(".hero__grid", {
    y: -48,
    ease: "none",
    scrollTrigger: { trigger: hero, start: "top top", end: "bottom top", scrub: true },
  });

  // Card tilt: small, only with a fine pointer that can hover.
  if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    document.querySelectorAll(".card__inner").forEach((card) => {
      const rx = gsap.quickTo(card, "rotationX", { duration: 0.6, ease: "power3.out" });
      const ry = gsap.quickTo(card, "rotationY", { duration: 0.6, ease: "power3.out" });
      const max = card.closest(".card--wide") ? 1.5 : 4;
      card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        ry(x * max * 2);
        rx(-y * max * 2);
      });
      card.addEventListener("pointerleave", () => {
        rx(0);
        ry(0);
      });
    });
  }
} else {
  root.classList.remove("motion");
}
