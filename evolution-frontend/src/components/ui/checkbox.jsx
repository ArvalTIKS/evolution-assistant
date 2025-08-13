import * as React from "react";
import { Check } from "lucide-react";

const Checkbox = React.forwardRef(({ className, ...props }, ref) => (
  <div className="form-check">
    <input
      ref={ref}
      type="checkbox"
      className={`form-check-input ${className || ''}`}
      {...props}
    />
    <label className="form-check-label">
      <Check className="h-4 w-4 d-none" />
    </label>
  </div>
));
Checkbox.displayName = "Checkbox";

export { Checkbox };