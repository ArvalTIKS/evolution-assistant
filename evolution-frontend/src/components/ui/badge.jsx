import * as React from "react";

const badgeVariants = {
  default: "badge bg-primary text-white",
  secondary: "badge bg-secondary text-white",
  destructive: "badge bg-danger text-white",
  outline: "badge border border-dark text-dark",
};

function Badge({ className, variant = "default", ...props }) {
  return (
    <span
      className={`${badgeVariants[variant] || badgeVariants.default} ${className || ''}`}
      {...props}
    />
  );
}

export { Badge, badgeVariants };