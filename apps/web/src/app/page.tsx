export default function HomePage() {
  return (
    <section
      aria-labelledby="page-title"
      className="max-w-190 rounded-xl border border-line-soft bg-surface p-[clamp(25px,5vw,54px)] shadow-[0_12px_34px_rgb(33_64_50/4%)]"
    >
      <p className="mb-4.75 flex items-center gap-2.25 text-2.5 font-bold tracking-[1.1px] text-accent uppercase">
        <span aria-hidden="true" className="h-px w-5 bg-accent" />
        Workspace setup
      </p>
      <h1
        className="m-0 font-display text-[clamp(36px,5.3vw,58px)] leading-[1.08] font-semibold tracking-[-3px] max-[1050px]:text-[clamp(36px,5vw,52px)] max-[760px]:text-[clamp(36px,9vw,52px)] max-[760px]:tracking-[-2.7px]"
        id="page-title"
      >
        Frontend foundation
      </h1>
      <p className="mt-4.5 mb-0 max-w-135 text-3.25 leading-[1.8] text-ink-soft">
        The application shell is ready to grow. Authentication, live recruiting
        data, and workflow screens will arrive in separate steps.
      </p>
    </section>
  );
}
