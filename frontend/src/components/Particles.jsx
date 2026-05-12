import { useRef } from "react";

export function Particles({ count = 12 }) {
  const particles = useRef(
    Array.from({ length: count }, () => ({
      left: Math.random() * 100,
      delay: Math.random() * -20,
      duration: 14 + Math.random() * 18,
      size: 1 + Math.random() * 2,
    }))
  ).current;

  return (
    <div className="particles" aria-hidden="true">
      {particles.map((particle, index) => (
        <span
          key={index}
          className="p"
          style={{
            left: `${particle.left}%`,
            bottom: "-24px",
            width: particle.size,
            height: particle.size,
            animationDelay: `${particle.delay}s`,
            animationDuration: `${particle.duration}s`,
          }}
        />
      ))}
    </div>
  );
}
