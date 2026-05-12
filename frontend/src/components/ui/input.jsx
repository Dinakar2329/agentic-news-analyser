import { cn } from "@/lib/utils";

export function Input({ className, type = "text", ...props }) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-white outline-none transition placeholder:text-neutral-500 focus:border-white/25 focus:bg-white/10",
        className
      )}
      {...props}
    />
  );
}
