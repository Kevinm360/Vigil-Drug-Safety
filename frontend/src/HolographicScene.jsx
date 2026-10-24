import React, { useEffect, useId, useRef, useState } from 'react';
import './HolographicScene.css';

// The SVG is also the instant first paint and the no-WebGL version of the scene.
function HolographicFallback() {
  const id = useId().replaceAll(':', '');
  return <svg className="holographic-fallback" viewBox="0 0 480 340" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-chrome`} x1="84" y1="55" x2="335" y2="272" gradientUnits="userSpaceOnUse">
        <stop stopColor="#FFF3FB"/><stop offset=".12" stopColor="#F7A1E9"/><stop offset=".23" stopColor="#8C65FF"/><stop offset=".36" stopColor="#51E5FF"/><stop offset=".48" stopColor="#BAFFF0"/><stop offset=".57" stopColor="#3463E9"/><stop offset=".68" stopColor="#885AFF"/><stop offset=".82" stopColor="#FFB4DA"/><stop offset=".92" stopColor="#D9CBFF"/><stop offset="1" stopColor="#6E81FF"/>
      </linearGradient>
      <linearGradient id={`${id}-edge`} x1="91" y1="135" x2="312" y2="226" gradientUnits="userSpaceOnUse"><stop stopColor="#E8FBFF"/><stop offset=".35" stopColor="#70F5F4"/><stop offset=".65" stopColor="#B789FF"/><stop offset="1" stopColor="#FFE9F4"/></linearGradient>
      <linearGradient id={`${id}-prism`} x1="337" y1="48" x2="428" y2="148" gradientUnits="userSpaceOnUse"><stop stopColor="#FAD4F1"/><stop offset=".44" stopColor="#BE9FFF"/><stop offset="1" stopColor="#4BD7FC"/></linearGradient>
      <radialGradient id={`${id}-orb`} cx=".3" cy=".22" r=".86"><stop stopColor="#F8EFFF"/><stop offset=".2" stopColor="#CDA8F6"/><stop offset=".43" stopColor="#9092FF"/><stop offset=".62" stopColor="#64DAEF"/><stop offset=".78" stopColor="#377EBA"/><stop offset=".94" stopColor="#8C5FE8"/><stop offset="1" stopColor="#D899EA"/></radialGradient>
      <radialGradient id={`${id}-glow`}><stop stopColor="#815FFF" stopOpacity=".38"/><stop offset="1" stopColor="#815FFF" stopOpacity="0"/></radialGradient>
      <filter id={`${id}-blur`}><feGaussianBlur stdDeviation="18"/></filter>
      <filter id={`${id}-gloss`} x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceAlpha" stdDeviation="2" result="blur"/><feSpecularLighting in="blur" surfaceScale="6" specularConstant=".7" specularExponent="22" lightingColor="#ffffff" result="shine"><fePointLight x="70" y="-80" z="180"/></feSpecularLighting><feComposite in="shine" in2="SourceAlpha" operator="in" result="shineClip"/><feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="shineClip"/></feMerge></filter>
    </defs>
    <ellipse cx="236" cy="187" rx="190" ry="136" fill={`url(#${id}-glow)`}/>
    <ellipse cx="216" cy="291" rx="112" ry="13" fill="#6863E8" opacity=".35" filter={`url(#${id}-blur)`}/>
    <g transform="rotate(-32 213 169)">
      <ellipse cx="213" cy="169" rx="126" ry="100" stroke="#261969" strokeWidth="45"/>
      <ellipse cx="211" cy="163" rx="126" ry="100" stroke={`url(#${id}-chrome)`} strokeWidth="39" filter={`url(#${id}-gloss)`}/>
      <ellipse cx="211" cy="163" rx="143" ry="118" stroke={`url(#${id}-edge)`} strokeOpacity=".9" strokeWidth="2.2"/>
      <ellipse cx="211" cy="166" rx="105" ry="79" stroke={`url(#${id}-edge)`} strokeWidth="2.6"/>
      <path d="M83 142C96 79 167 39 225 54" stroke="#FFF5FF" strokeWidth="3" strokeLinecap="round" opacity=".8"/>
      <path d="M100 184C104 205 122 226 142 238" stroke="#79FFFF" strokeWidth="6" strokeLinecap="round" opacity=".85"/>
    </g>
    <g stroke="#D5D0FF" strokeWidth=".8" strokeLinejoin="round">
      <path d="M379 39L431 111L362 143L332 87Z" fill={`url(#${id}-prism)`}/>
      <path d="M379 39L385 102L332 87Z" fill="#F6BEDF"/>
      <path d="M379 39L431 111L385 102Z" fill="#A9C7FF"/>
      <path d="M332 87L385 102L362 143Z" fill="#8363F0"/>
      <path d="M385 102L431 111L362 143Z" fill="#66E5EF"/>
      <path d="M379 39L385 102L362 143" stroke="#B7FFF9" strokeWidth="1.4"/>
    </g>
    <circle cx="374" cy="264" r="38" fill={`url(#${id}-orb)`} stroke="#C9C4FF" strokeOpacity=".55"/>
    <path d="M350 250C350 240 358 233 366 232" stroke="#FFF0FF" strokeWidth="3" strokeLinecap="round" opacity=".85"/>
    <ellipse cx="374" cy="272" rx="35" ry="14" stroke="#8CF7FF" strokeOpacity=".5" transform="rotate(-25 374 272)"/>
    <g fill="#D8D9FF"><circle cx="96" cy="58" r="2"/><circle cx="314" cy="286" r="2"/><circle cx="450" cy="190" r="1.6"/></g>
    <path d="M310 40V50M305 45H315M85 265V273M81 269H89" stroke="#BFD1FF" strokeWidth="1.3" strokeLinecap="round"/>
  </svg>;
}

export default function HolographicScene({ className = '' }) {
  const hostRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    let disposed = false;
    let cleanup = () => {};

    async function initialize() {
      const THREE = await import('three');
      if (disposed || !host) return;

      let renderer;
      try {
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
      } catch {
        return; // Keep the illustrated fallback on devices without WebGL.
      }
      if (disposed) { renderer.dispose(); return; }

      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.03;
      renderer.domElement.className = 'holographic-canvas';
      renderer.domElement.setAttribute('aria-hidden', 'true');
      host.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(36, 1, .1, 50);
      camera.position.set(0, .04, 7.25);
      const stage = new THREE.Group();
      scene.add(stage);
      const resources = [];
      const keep = (resource) => { resources.push(resource); return resource; };
      let released = false;
      const release = () => {
        if (released) return;
        released = true;
        scene.environment = null;
        for (const resource of resources) resource.dispose();
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      };
      cleanup = release;

      // A local studio environment supplies real, colorful chrome reflections.
      // It is generated at runtime; no image downloads or network are needed.
      const studio = document.createElement('canvas');
      studio.width = 1024;
      studio.height = 512;
      const ctx = studio.getContext('2d');
      if (!ctx) { release(); return; }
      ctx.fillStyle = '#27344f';
      ctx.fillRect(0, 0, 1024, 512);
      const wash = ctx.createLinearGradient(0, 0, 1024, 512);
      wash.addColorStop(0, '#4940a9');
      wash.addColorStop(.18, '#251358');
      wash.addColorStop(.38, '#08cbdc');
      wash.addColorStop(.53, '#7362c0');
      wash.addColorStop(.7, '#4320a7');
      wash.addColorStop(.86, '#ec6bbd');
      wash.addColorStop(1, '#334d9e');
      ctx.fillStyle = wash;
      ctx.fillRect(0, 0, 1024, 512);
      const panel = (x, y, w, h, color, blur = 0) => {
        ctx.save();
        ctx.filter = `blur(${blur}px)`;
        ctx.fillStyle = color;
        ctx.fillRect(x, y, w, h);
        ctx.restore();
      };
      panel(42, 20, 64, 365, '#f9eaff', 4);
      panel(126, 20, 22, 390, '#071023', 1);
      panel(162, 30, 42, 320, '#31ffff', 3);
      panel(282, 0, 92, 160, '#e8e0ff', 6);
      panel(423, 70, 80, 390, '#070e29', 2);
      panel(530, 0, 77, 350, '#ff69ca', 4);
      panel(628, 80, 26, 380, '#17102e', 1);
      panel(674, 0, 18, 420, '#fff5fb', 2);
      panel(713, 170, 110, 160, '#6e55ff', 5);
      panel(854, 40, 26, 360, '#071127', 1);
      panel(911, 15, 51, 385, '#b3f6ff', 4);
      panel(0, 425, 1024, 87, '#050b1c', 8);
      const environment = keep(new THREE.CanvasTexture(studio));
      environment.mapping = THREE.EquirectangularReflectionMapping;
      environment.colorSpace = THREE.SRGBColorSpace;
      const pmrem = new THREE.PMREMGenerator(renderer);
      const environmentMap = keep(pmrem.fromEquirectangular(environment));
      scene.environment = environmentMap.texture;
      pmrem.dispose();

      scene.add(new THREE.AmbientLight(0xc0ccff, .4));
      const key = new THREE.DirectionalLight(0xffeffb, 2.2);
      key.position.set(-3, 5, 5);
      scene.add(key);
      const cyan = new THREE.DirectionalLight(0x25edff, 2.4);
      cyan.position.set(-4, -.5, 2);
      scene.add(cyan);
      const pink = new THREE.DirectionalLight(0xf87bff, 2.6);
      pink.position.set(4, 2, -1);
      scene.add(pink);

      const pearl = keep(new THREE.MeshPhysicalMaterial({
        color: 0xffffff, metalness: .96, roughness: .075,
        clearcoat: 1, clearcoatRoughness: .035,
        iridescence: .5, iridescenceIOR: 1.45,
        iridescenceThicknessRange: [110, 530],
        envMapIntensity: 1.7, vertexColors: true,
      }));
      const torusGeometry = keep(new THREE.TorusGeometry(1.13, .315, 48, 160));
      const positions = torusGeometry.attributes.position;
      const colors = [];
      const color = new THREE.Color();
      for (let i = 0; i < positions.count; i++) {
        const x = positions.getX(i), y = positions.getY(i), a = Math.atan2(y, x);
        const ripple = 1 + .025 * Math.sin(a * 3);
        positions.setXYZ(i, x * ripple, y * ripple, positions.getZ(i) + .052 * Math.sin(a * 2));
        color.setHSL(.675 + .155 * Math.sin(a + .8), .88, .57);
        colors.push(color.r, color.g, color.b);
      }
      torusGeometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
      torusGeometry.computeVertexNormals();
      const ring = new THREE.Mesh(torusGeometry, pearl);
      const ringGroup = new THREE.Group();
      ringGroup.add(ring);
      const innerRimGeometry = keep(new THREE.TorusGeometry(.816, .013, 8, 160));
      const rimPositions = innerRimGeometry.attributes.position;
      for (let i = 0; i < rimPositions.count; i++) {
        const x = rimPositions.getX(i), y = rimPositions.getY(i), a = Math.atan2(y, x);
        const ripple = 1 + .025 * Math.sin(a * 3);
        rimPositions.setXYZ(i, x * ripple, y * ripple, rimPositions.getZ(i) + .052 * Math.sin(a * 2));
      }
      innerRimGeometry.computeVertexNormals();
      const rimMaterial = keep(new THREE.MeshPhysicalMaterial({
        color: 0x45e5ff, emissive: 0x005b7a, emissiveIntensity: .28,
        metalness: .82, roughness: .08, clearcoat: 1, envMapIntensity: 1.5,
      }));
      ringGroup.add(new THREE.Mesh(innerRimGeometry, rimMaterial));
      ringGroup.position.set(-.35, .02, .05);
      ringGroup.rotation.set(.53, -.46, -.47);
      ringGroup.scale.setScalar(1.12);
      stage.add(ringGroup);

      const prismMaterial = keep(new THREE.MeshPhysicalMaterial({
        color: 0xffffff, metalness: .56, roughness: .085,
        clearcoat: 1, iridescence: .6, iridescenceIOR: 1.5,
        iridescenceThicknessRange: [130, 580], envMapIntensity: 1.5,
        flatShading: true, vertexColors: true,
      }));
      const prismGeometry = keep(new THREE.OctahedronGeometry(.48, 0));
      const prismColors = [];
      const facetPalette = ['#d68cf7', '#4de4ff', '#8054ed', '#f797d5'].map(value => new THREE.Color(value));
      for (let i = 0; i < prismGeometry.attributes.position.count; i++) {
        const facet = facetPalette[Math.floor(i / 3) % facetPalette.length];
        prismColors.push(facet.r, facet.g, facet.b);
      }
      prismGeometry.setAttribute('color', new THREE.Float32BufferAttribute(prismColors, 3));
      const prism = new THREE.Mesh(prismGeometry, prismMaterial);
      prism.position.set(1.46, 1.05, -.1);
      prism.rotation.set(.3, .4, -.3);
      stage.add(prism);

      const orbMaterial = keep(new THREE.MeshPhysicalMaterial({
        color: 0x8c7df9, metalness: .62, roughness: .065,
        clearcoat: 1, clearcoatRoughness: .03,
        iridescence: 1, iridescenceIOR: 1.4,
        iridescenceThicknessRange: [80, 480], envMapIntensity: 1.45,
      }));
      const orb = new THREE.Mesh(keep(new THREE.SphereGeometry(.34, 40, 32)), orbMaterial);
      orb.position.set(1.35, -1.04, .32);
      stage.add(orb);

      const orbitMaterial = keep(new THREE.MeshBasicMaterial({ color: 0x9cefff, transparent: true, opacity: .6 }));
      const orbit = new THREE.Mesh(keep(new THREE.TorusGeometry(.43, .009, 8, 64)), orbitMaterial);
      orbit.rotation.set(1.0, -.28, -.45);
      orb.add(orbit);

      const particles = keep(new THREE.BufferGeometry());
      particles.setAttribute('position', new THREE.Float32BufferAttribute([
        -1.75, 1.12, -.2, 1.89, -.03, -.3, .66, -1.39, .2,
        -.8, -1.48, -.3, .68, 1.43, -.2,
      ], 3));
      const particleMaterial = keep(new THREE.PointsMaterial({ color: 0xc2d0ff, size: .023, transparent: true, opacity: .8, sizeAttenuation: true }));
      stage.add(new THREE.Points(particles, particleMaterial));

      const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
      let reduced = motion.matches;
      let inView = true;
      let lost = false;
      let frame = 0;
      let previousTime = 0;
      let elapsed = 0;
      let pointerX = 0, pointerY = 0;
      let currentX = 0, currentY = 0;
      const canAnimate = () => !disposed && !lost && !document.hidden && inView && !reduced;

      const draw = (time = 0) => {
        frame = 0;
        if (disposed || lost) return;
        const delta = previousTime ? Math.min((time - previousTime) / 1000, .05) : 0;
        previousTime = time;
        if (!reduced) elapsed += delta;
        currentX += (pointerX - currentX) * .055;
        currentY += (pointerY - currentY) * .055;
        stage.rotation.y = reduced ? 0 : currentX * .16;
        stage.rotation.x = reduced ? 0 : -currentY * .1;
        ringGroup.rotation.y = -.46 + Math.sin(elapsed * .22) * .16;
        ringGroup.rotation.z = -.47 + Math.sin(elapsed * .17) * .06;
        ringGroup.position.y = .02 + Math.sin(elapsed * .52) * .055;
        prism.rotation.y = .4 + elapsed * .13;
        prism.position.y = 1.05 + Math.sin(elapsed * .65 + .8) * .07;
        orb.position.y = -1.04 + Math.sin(elapsed * .62 + 2) * .045;
        orb.rotation.y = elapsed * .12;
        renderer.render(scene, camera);
        if (canAnimate()) frame = requestAnimationFrame(draw);
      };
      const resume = () => {
        previousTime = 0;
        if (canAnimate() && !frame) frame = requestAnimationFrame(draw);
      };
      const stop = () => { cancelAnimationFrame(frame); frame = 0; previousTime = 0; };
      const resize = () => {
        if (disposed || lost) return;
        const { width, height } = host.getBoundingClientRect();
        if (width < 1 || height < 1) return;
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        // Keep all three forms in frame in narrower hero layouts.
        camera.position.z = camera.aspect < 1.25 ? 7.25 * (1.25 / camera.aspect) : 7.25;
        camera.updateProjectionMatrix();
        if (!frame) draw();
      };
      const onPointer = (event) => {
        if (reduced) return;
        const rect = host.getBoundingClientRect();
        pointerX = ((event.clientX - rect.left) / rect.width - .5) * 2;
        pointerY = ((event.clientY - rect.top) / rect.height - .5) * 2;
      };
      const onLeave = () => { pointerX = 0; pointerY = 0; };
      const onVisibility = () => { if (document.hidden) stop(); else resume(); };
      const onMotion = () => { reduced = motion.matches; stop(); if (reduced) draw(); else resume(); };
      const onContextLost = (event) => { event.preventDefault(); lost = true; stop(); if (!disposed) setReady(false); };
      const resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(host);
      const intersectionObserver = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver(([entry]) => {
        inView = entry.isIntersecting;
        if (inView) resume(); else stop();
      });
      intersectionObserver?.observe(host);
      host.addEventListener('pointermove', onPointer, { passive: true });
      host.addEventListener('pointerleave', onLeave);
      document.addEventListener('visibilitychange', onVisibility);
      motion.addEventListener('change', onMotion);
      renderer.domElement.addEventListener('webglcontextlost', onContextLost);

      cleanup = () => {
        stop();
        resizeObserver.disconnect();
        intersectionObserver?.disconnect();
        host.removeEventListener('pointermove', onPointer);
        host.removeEventListener('pointerleave', onLeave);
        document.removeEventListener('visibilitychange', onVisibility);
        motion.removeEventListener('change', onMotion);
        renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
        release();
      };
      resize();
      setReady(true);
    }

    initialize().catch(() => { cleanup(); if (!disposed) setReady(false); });
    return () => { disposed = true; cleanup(); };
  }, []);

  return <div ref={hostRef} className={`holographic-scene ${ready ? 'is-ready' : ''} ${className}`} aria-hidden="true">
    <HolographicFallback />
    <span className="holographic-star holographic-star-one" />
    <span className="holographic-star holographic-star-two" />
  </div>;
}
