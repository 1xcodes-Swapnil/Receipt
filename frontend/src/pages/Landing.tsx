import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Play, Zap } from 'lucide-react';
import { LandingHero } from '../components/landing/LandingHero';
import { LandingSections } from '../components/landing/LandingSections';

export default function Landing() {
  return (
    <div className="w-[98%] mx-auto px-3 sm:px-4 lg:px-6 py-8 space-y-10">
      <LandingHero />
      <LandingSections />

      <section className="relative overflow-hidden rounded-[2rem] sm:rounded-[2.5rem] border border-brand-200/80 bg-gradient-to-b from-brand-100 to-brand-50 shadow-soft-xl px-6 sm:px-10 lg:px-14 py-12 sm:py-16 text-center">
        <div className="absolute inset-0 bg-evidence-grid pointer-events-none" />
        <div className="relative max-w-2xl mx-auto space-y-5">
          <h2 className="font-serif-title font-bold text-3xl sm:text-5xl text-brand-950 leading-tight">
            Review with <span className="italic font-medium text-brand-700">receipts.</span>
          </h2>
          <p className="text-sm sm:text-base text-brand-700 leading-relaxed">
            Run the four agents against a pull request and get a verdict you can verify, replay, and audit.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
            <Link to="/review" className="btn-pill-primary px-7 py-3.5 w-full sm:w-auto">
              <Zap className="w-4 h-4 text-amber-300" />
              Start a Review
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link to="/demo" className="btn-pill-secondary px-7 py-3.5 w-full sm:w-auto">
              <Play className="w-4 h-4 fill-current text-brand-600" />
              Explore Demo
            </Link>
            <Link to="/dashboard" className="btn-pill-secondary px-7 py-3.5 w-full sm:w-auto">
              <Activity className="w-4 h-4 text-brand-600" />
              Open Dashboard
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
