import * as React from "react";

const buttonVariants = {
  default: "btn btn-primary",
  destructive: "btn btn-danger",
  outline: "btn btn-outline-secondary",
  secondary: "btn btn-secondary",
  ghost: "btn btn-link",
  link: "btn btn-link text-decoration-underline",
  sizes: {
    default: "",
    sm: "btn-sm",
    lg: "btn-lg",
    icon: "btn-square",
  },
};

const Button = React.forwardRef(({ className, variant = "default", size = "default", asChild = false, ...props }, ref) => {
  const Comp = asChild ? "span" : "button";
  const variantClass = buttonVariants[variant] || buttonVariants.default;
  const sizeClass = buttonVariants.sizes[size] || buttonVariants.sizes.default;

  return (
    <Comp
      className={`${variantClass} ${sizeClass} d-flex align-items-center gap-2 ${className || ''}`}
      ref={ref}
      {...props}
    />
  );
});
Button.displayName = "Button";

export { Button, buttonVariants };