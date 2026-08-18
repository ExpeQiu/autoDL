import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-40 outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60",
  {
    variants: {
      variant: {
        default: "bg-amber-500 text-stone-950 hover:bg-amber-400",
        outline: "border border-stone-700 bg-transparent text-stone-200 hover:bg-stone-800",
        ghost: "text-stone-300 hover:bg-stone-800",
        destructive: "border border-red-900/80 bg-transparent text-red-300 hover:bg-red-950/70",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3 text-xs",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
