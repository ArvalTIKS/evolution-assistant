import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";

const Label = React.forwardRef(({ className = "", ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={`form-label fw-medium mb-1 ${className}`}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
