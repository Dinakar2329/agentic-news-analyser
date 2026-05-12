import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-24 w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none transition placeholder:text-neutral-500 focus:border-white/25 focus:bg-white/10",
        className
      )}
      {...props}
    />
  );
}
