/* ═══════════════════════════════════════════════════════
   AI-SALES ANALYTICS AGENT — PREMIUM LANDING PAGE JAVASCRIPT
   Custom animations: Intersection Observer, rAF, cubic-bezier
   Zero animation libraries. All hand-crafted.
   ═══════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ─── Utility: Debounce ───
    function debounce(fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    // ─── Utility: Lerp ───
    function lerp(a, b, t) {
        return a + (b - a) * t;
    }

    // ═══════════════════════════════════════════
    //  NAVBAR SCROLL EFFECT
    // ═══════════════════════════════════════════
    const navbar = document.getElementById('navbar');
    let lastScrollY = 0;

    function handleNavScroll() {
        const sy = window.scrollY;
        if (sy > 40) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
        lastScrollY = sy;
    }

    window.addEventListener('scroll', debounce(handleNavScroll, 10), { passive: true });
    handleNavScroll();

    // Mobile toggle
    const mobileToggle = document.getElementById('mobileToggle');
    const navLinks = document.getElementById('navLinks');

    if (mobileToggle) {
        mobileToggle.addEventListener('click', () => {
            mobileToggle.classList.toggle('active');
            navLinks.classList.toggle('mobile-open');
        });
    }

    // ═══════════════════════════════════════════
    //  HERO — CINEMATIC INTRO SEQUENCE
    // ═══════════════════════════════════════════

    function initHeroSequence() {
        const heroTitle = document.getElementById('heroTitle');
        const heroSubtitle = document.getElementById('heroSubtitle');
        const heroBadge = document.querySelector('.hero-badge');
        const heroCtas = document.querySelector('.hero-ctas');
        const heroStats = document.querySelector('.hero-stats');
        const heroVisual = document.getElementById('heroVisual');

        if (!heroTitle) return;

        // Split title into spans per character
        const text = heroTitle.textContent.trim();
        heroTitle.innerHTML = '';
        const words = text.split(/\s+/);
        let charIndex = 0;
        words.forEach((word, wi) => {
            const wordSpan = document.createElement('span');
            wordSpan.className = 'word';
            for (let i = 0; i < word.length; i++) {
                const charSpan = document.createElement('span');
                charSpan.className = 'char';
                charSpan.textContent = word[i];
                charSpan.style.transitionDelay = `${charIndex * 25 + 400}ms`;
                wordSpan.appendChild(charSpan);
                charIndex++;
            }
            heroTitle.appendChild(wordSpan);
            // Add space between words
            if (wi < words.length - 1) {
                heroTitle.appendChild(document.createTextNode(' '));
            }
        });

        // Staggered timeline
        const timeline = [
            { el: heroBadge, delay: 200 },
            { el: null, delay: 400, action: () => heroTitle.querySelectorAll('.char').forEach(c => c.classList.add('revealed')) },
            { el: heroSubtitle, delay: 1200 },
            { el: heroCtas, delay: 1500 },
            { el: heroStats, delay: 1800 },
            { el: heroVisual, delay: 2200, cls: 'revealed' }
        ];

        timeline.forEach(({ el, delay, action, cls }) => {
            setTimeout(() => {
                if (action) return action();
                if (el) {
                    el.style.transition = `opacity 0.8s cubic-bezier(0.16,1,0.3,1), transform 0.8s cubic-bezier(0.16,1,0.3,1)`;
                    el.style.opacity = '1';
                    el.style.transform = 'translateY(0)';
                    if (cls) el.classList.add(cls);
                }
            }, delay);
        });

        // Animate chart lines in hero mockup after visual reveals
        setTimeout(() => {
            document.querySelectorAll('.chart-line').forEach(l => l.classList.add('animated'));
            document.querySelectorAll('.chart-area-path').forEach(l => l.classList.add('animated'));
            document.querySelectorAll('.msc-bar-fill').forEach(l => l.classList.add('animated'));
        }, 2800);
    }

    // ═══════════════════════════════════════════
    //  HERO STATS — COUNT UP
    // ═══════════════════════════════════════════

    function animateCountUp(el, target, duration) {
        const start = performance.now();
        const initial = 0;

        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            // Ease out quart
            const eased = 1 - Math.pow(1 - progress, 4);
            const current = Math.floor(initial + (target - initial) * eased);
            el.textContent = current.toLocaleString();
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }

        requestAnimationFrame(update);
    }

    function initHeroCounters() {
        const statNumbers = document.querySelectorAll('.hero-stat .stat-number');
        // Wait for hero sequence
        setTimeout(() => {
            statNumbers.forEach(el => {
                const target = parseInt(el.dataset.target, 10);
                animateCountUp(el, target, 2000);
            });
        }, 2200);
    }

    // ═══════════════════════════════════════════
    //  HERO 3D TILT EFFECT
    // ═══════════════════════════════════════════

    const heroVisualEl = document.getElementById('heroVisual');
    let tiltX = 0, tiltY = 0, currentTiltX = 0, currentTiltY = 0;

    function handleMouseMove(e) {
        if (!heroVisualEl || window.innerWidth < 768) return;
        const rect = heroVisualEl.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        tiltX = ((e.clientY - cy) / rect.height) * 6;
        tiltY = ((e.clientX - cx) / rect.width) * -6;
    }

    function tiltLoop() {
        currentTiltX = lerp(currentTiltX, tiltX, 0.08);
        currentTiltY = lerp(currentTiltY, tiltY, 0.08);
        if (heroVisualEl) {
            const mockup = heroVisualEl.querySelector('.dashboard-mockup');
            if (mockup) {
                mockup.style.transform = `rotateX(${4 + currentTiltX}deg) rotateY(${currentTiltY}deg)`;
            }
        }
        requestAnimationFrame(tiltLoop);
    }

    document.addEventListener('mousemove', handleMouseMove, { passive: true });
    tiltLoop();

    // ═══════════════════════════════════════════
    //  SCROLL REVEAL (Intersection Observer)
    // ═══════════════════════════════════════════

    function initScrollReveals() {
        const revealElements = document.querySelectorAll('.reveal-up');

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const delay = parseInt(entry.target.dataset.delay || '0', 10);
                    setTimeout(() => {
                        entry.target.classList.add('revealed');
                    }, delay);
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.15,
            rootMargin: '0px 0px -60px 0px'
        });

        revealElements.forEach(el => observer.observe(el));
    }

    // ═══════════════════════════════════════════
    //  SHOWCASE — METRICS & CHARTS ANIMATION
    // ═══════════════════════════════════════════

    function initShowcaseAnimations() {
        const showcaseSection = document.getElementById('showcase');
        if (!showcaseSection) return;

        const metrics = showcaseSection.querySelectorAll('.showcase-metric');
        const scLines = showcaseSection.querySelectorAll('.sc-line, .sc-line-2');
        const scArea = showcaseSection.querySelectorAll('.sc-area');
        const counters = showcaseSection.querySelectorAll('.counter');

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Stagger metrics
                    metrics.forEach((m, i) => {
                        const d = parseInt(m.dataset.delay || '0', 10);
                        setTimeout(() => m.classList.add('revealed'), d + 200);
                    });

                    // Animate chart lines
                    setTimeout(() => {
                        scLines.forEach(l => l.classList.add('animated'));
                        scArea.forEach(a => a.classList.add('animated'));
                    }, 600);

                    // Count up counters
                    counters.forEach((c, i) => {
                        setTimeout(() => {
                            const target = parseInt(c.dataset.target, 10);
                            const prefix = c.dataset.prefix || '';
                            const suffix = c.dataset.suffix || '';
                            animateCounterElement(c, target, 1800, prefix, suffix);
                        }, 400 + i * 150);
                    });

                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.2 });

        observer.observe(showcaseSection);
    }

    function animateCounterElement(el, target, duration, prefix, suffix) {
        const start = performance.now();
        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 4);
            const current = Math.floor(target * eased);
            el.textContent = prefix + current.toLocaleString() + suffix;
            if (progress < 1) requestAnimationFrame(update);
        }
        requestAnimationFrame(update);
    }

    // ═══════════════════════════════════════════
    //  TECH STACK — APPEAR/HOLD/DISAPPEAR
    // ═══════════════════════════════════════════

    function initTechStackAnimations() {
        const section = document.getElementById('techstack');
        if (!section) return;

        const cards = section.querySelectorAll('.tech-card');

        // Set initial state
        cards.forEach(card => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(30px) scale(0.96)';
            card.style.transition = 'none';
        });

        let hasAppeared = false;

        const appearObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !hasAppeared) {
                    hasAppeared = true;
                    cards.forEach((card, i) => {
                        setTimeout(() => {
                            card.style.transition = 'opacity 0.7s cubic-bezier(0.16,1,0.3,1), transform 0.7s cubic-bezier(0.16,1,0.3,1)';
                            card.style.opacity = '1';
                            card.style.transform = 'translateY(0) scale(1)';
                        }, i * 80);
                    });
                    appearObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.2 });

        appearObserver.observe(section);

        // Parallax depth on scroll using rAF
        let techScrollProgress = 0;
        let currentProgress = 0;
        let techRafId;

        function updateTechParallax() {
            currentProgress = lerp(currentProgress, techScrollProgress, 0.1);
            cards.forEach((card, i) => {
                const offset = (i % 3 - 1) * currentProgress * 12;
                const scale = 1 - Math.abs(currentProgress - 0.5) * 0.04;
                if (hasAppeared) {
                    card.style.transform = `translateY(${offset}px) scale(${scale})`;
                }
            });
            techRafId = requestAnimationFrame(updateTechParallax);
        }

        const scrollHandler = () => {
            const rect = section.getBoundingClientRect();
            const vh = window.innerHeight;
            techScrollProgress = Math.max(0, Math.min(1, 1 - (rect.top + rect.height) / (vh + rect.height)));
        };

        window.addEventListener('scroll', scrollHandler, { passive: true });
        updateTechParallax();
    }

    // ═══════════════════════════════════════════
    //  PRICING TOGGLE
    // ═══════════════════════════════════════════

    function initPricingToggle() {
        const toggle = document.getElementById('pricingToggle');
        if (!toggle) return;

        const labels = document.querySelectorAll('.toggle-label');
        const amounts = document.querySelectorAll('.price-amount');
        let isYearly = false;

        toggle.addEventListener('click', () => {
            isYearly = !isYearly;
            toggle.classList.toggle('active', isYearly);
            labels[0].setAttribute('data-active', !isYearly);
            labels[1].setAttribute('data-active', isYearly);

            // Animate price change
            amounts.forEach(el => {
                el.classList.add('changing');
                setTimeout(() => {
                    const val = isYearly ? el.dataset.yearly : el.dataset.monthly;
                    el.textContent = val;
                    el.classList.remove('changing');
                }, 250);
            });
        });
    }

    // ═══════════════════════════════════════════
    //  TESTIMONIALS — rAF INFINITE SCROLL
    // ═══════════════════════════════════════════

    function initTestimonialCarousel() {
        const track = document.getElementById('testimonialTrack');
        if (!track) return;

        // Duplicate cards for seamless loop
        const cards = track.innerHTML;
        track.innerHTML = cards + cards;

        let position = 0;
        let speed = 0.5;
        let isPaused = false;
        let targetSpeed = 0.5;
        const totalWidth = track.scrollWidth / 2;

        function animate() {
            if (!isPaused) {
                speed = lerp(speed, targetSpeed, 0.05);
            } else {
                speed = lerp(speed, 0, 0.08);
            }

            position -= speed;
            if (Math.abs(position) >= totalWidth) {
                position = 0;
            }

            track.style.transform = `translateX(${position}px)`;
            requestAnimationFrame(animate);
        }

        track.addEventListener('mouseenter', () => { isPaused = true; });
        track.addEventListener('mouseleave', () => { isPaused = false; });
        track.addEventListener('touchstart', () => { isPaused = true; }, { passive: true });
        track.addEventListener('touchend', () => { isPaused = false; });

        requestAnimationFrame(animate);
    }

    // ═══════════════════════════════════════════
    //  CTA — STAGGERED HEADLINE REVEAL
    // ═══════════════════════════════════════════

    function initCtaReveal() {
        const ctaTitle = document.getElementById('ctaTitle');
        if (!ctaTitle) return;

        const ctaSection = document.getElementById('cta');

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // Already handled by reveal-up on parent
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.2 });

        observer.observe(ctaSection);
    }

    // ═══════════════════════════════════════════
    //  SMOOTH ANCHOR SCROLLING
    // ═══════════════════════════════════════════

    function initSmoothAnchors() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', (e) => {
                e.preventDefault();
                const target = document.querySelector(anchor.getAttribute('href'));
                if (target) {
                    // Close mobile menu
                    if (navLinks) navLinks.classList.remove('mobile-open');
                    if (mobileToggle) mobileToggle.classList.remove('active');

                    const top = target.getBoundingClientRect().top + window.scrollY - 80;
                    window.scrollTo({ top, behavior: 'smooth' });
                }
            });
        });
    }

    // ═══════════════════════════════════════════
    //  HERO DOTTED BACKGROUND — Interactive Grid
    // ═══════════════════════════════════════════

    function initHeroDots() {
        const canvas = document.getElementById('heroDotsCanvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        let dots = [];
        let mouse = { x: -9999, y: -9999 };
        const SPACING = 32;
        const DOT_RADIUS = 1.2;
        const INFLUENCE_RADIUS = 150;
        const MAX_SCALE = 3.5;
        const MAX_ALPHA = 0.7;
        const BASE_ALPHA = 0.12;

        function resize() {
            const hero = document.getElementById('hero');
            const rect = hero.getBoundingClientRect();
            canvas.width = rect.width * window.devicePixelRatio;
            canvas.height = rect.height * window.devicePixelRatio;
            canvas.style.width = rect.width + 'px';
            canvas.style.height = rect.height + 'px';
            ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
            buildGrid(rect.width, rect.height);
        }

        function buildGrid(w, h) {
            dots = [];
            const cols = Math.ceil(w / SPACING) + 1;
            const rows = Math.ceil(h / SPACING) + 1;
            const offsetX = (w - (cols - 1) * SPACING) / 2;
            const offsetY = (h - (rows - 1) * SPACING) / 2;
            for (let r = 0; r < rows; r++) {
                for (let c = 0; c < cols; c++) {
                    dots.push({
                        x: offsetX + c * SPACING,
                        y: offsetY + r * SPACING,
                        scale: 1,
                        alpha: BASE_ALPHA
                    });
                }
            }
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width / window.devicePixelRatio, canvas.height / window.devicePixelRatio);

            const isLight = document.body.classList.contains('light-theme');
            const dotColor = isLight ? '30, 30, 60' : '200, 200, 255';

            for (let i = 0; i < dots.length; i++) {
                const d = dots[i];
                const dx = mouse.x - d.x;
                const dy = mouse.y - d.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                let targetScale = 1;
                let targetAlpha = BASE_ALPHA;

                if (dist < INFLUENCE_RADIUS) {
                    const t = 1 - dist / INFLUENCE_RADIUS;
                    // Smooth cubic ease
                    const eased = t * t * (3 - 2 * t);
                    targetScale = 1 + (MAX_SCALE - 1) * eased;
                    targetAlpha = BASE_ALPHA + (MAX_ALPHA - BASE_ALPHA) * eased;
                }

                d.scale = lerp(d.scale, targetScale, 0.15);
                d.alpha = lerp(d.alpha, targetAlpha, 0.15);

                const r = DOT_RADIUS * d.scale;
                ctx.beginPath();
                ctx.arc(d.x, d.y, r, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(${dotColor}, ${d.alpha})`;
                ctx.fill();
            }
            requestAnimationFrame(draw);
        }

        const heroEl = document.getElementById('hero');
        heroEl.addEventListener('mousemove', (e) => {
            const rect = heroEl.getBoundingClientRect();
            mouse.x = e.clientX - rect.left;
            mouse.y = e.clientY - rect.top;
        }, { passive: true });

        heroEl.addEventListener('mouseleave', () => {
            mouse.x = -9999;
            mouse.y = -9999;
        });

        window.addEventListener('resize', debounce(resize, 200));
        resize();
        requestAnimationFrame(draw);
    }

    // ═══════════════════════════════════════════
    //  PARALLAX ORBS — Subtle mouse response
    // ═══════════════════════════════════════════

    let mouseX = 0, mouseY = 0, orbX = 0, orbY = 0;

    function initOrbParallax() {
        document.addEventListener('mousemove', (e) => {
            mouseX = (e.clientX / window.innerWidth - 0.5) * 30;
            mouseY = (e.clientY / window.innerHeight - 0.5) * 30;
        }, { passive: true });

        const orbs = document.querySelectorAll('.orb');

        function orbLoop() {
            orbX = lerp(orbX, mouseX, 0.03);
            orbY = lerp(orbY, mouseY, 0.03);

            orbs.forEach((orb, i) => {
                const factor = (i + 1) * 0.5;
                orb.style.transform = `translate(${orbX * factor}px, ${orbY * factor}px)`;
            });
            requestAnimationFrame(orbLoop);
        }
        orbLoop();
    }

    // ═══════════════════════════════════════════
    //  TUTORIAL MODAL
    // ═══════════════════════════════════════════

    function initTutorialModal() {
        const btn = document.getElementById('tutorialBtn');
        const overlay = document.getElementById('tutorialOverlay');
        const closeBtn = document.getElementById('tutorialClose');
        if (!btn || !overlay) return;

        function openModal() {
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeModal() {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }

        btn.addEventListener('click', openModal);
        closeBtn.addEventListener('click', closeModal);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('active')) {
                closeModal();
            }
        });
    }

    // ═══════════════════════════════════════════
    //  GO TO TOP BUTTON
    // ═══════════════════════════════════════════

    function initGoTopButton() {
        const btn = document.getElementById('goTopBtn');
        if (!btn) return;

        window.addEventListener('scroll', debounce(() => {
            if (window.scrollY > 400) {
                btn.classList.add('visible');
            } else {
                btn.classList.remove('visible');
            }
        }, 10), { passive: true });

        btn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // ═══════════════════════════════════════════
    //  THEME TOGGLE (Light / Dark)
    // ═══════════════════════════════════════════

    function initThemeToggle() {
        const toggle = document.getElementById('landingThemeToggle');
        if (!toggle) return;

        const saved = localStorage.getItem('landing-theme');
        // Default is dark (unchecked). Checked = light.
        if (saved === 'light') {
            document.body.classList.add('light-theme');
            toggle.checked = true;
        }

        toggle.addEventListener('change', () => {
            document.body.classList.toggle('light-theme', toggle.checked);
            localStorage.setItem('landing-theme', toggle.checked ? 'light' : 'dark');
        });
    }

    // ═══════════════════════════════════════════
    //  INITIALIZE EVERYTHING
    // ═══════════════════════════════════════════

    document.addEventListener('DOMContentLoaded', () => {
        initHeroSequence();
        initHeroCounters();
        initScrollReveals();
        initShowcaseAnimations();
        initTechStackAnimations();
        initPricingToggle();
        initTestimonialCarousel();
        initCtaReveal();
        initSmoothAnchors();
        initOrbParallax();
        initHeroDots();
        initTutorialModal();
        initGoTopButton();
        initThemeToggle();
    });
})();
