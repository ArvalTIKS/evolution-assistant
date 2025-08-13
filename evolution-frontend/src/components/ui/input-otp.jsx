import * as React from "react";
import { OTPInput, OTPInputContext } from "input-otp";
import { Minus } from "lucide-react";

const InputOTP = React.forwardRef(({ className = "", containerClassName = "", ...props }, ref) => (
  <OTPInput
    ref={ref}
    containerClassName={`d-flex align-items-center gap-2 ${containerClassName}`}
    className={`disabled ${className}`}
    {...props}
  />
));
InputOTP.displayName = "InputOTP";

const InputOTPGroup = React.forwardRef(({ className = "", ...props }, ref) => (
  <div ref={ref} className={`d-flex align-items-center ${className}`} {...props} />
));
InputOTPGroup.displayName = "InputOTPGroup";

const InputOTPSlot = React.forwardRef(({ index, className = "", ...props }, ref) => {
  const inputOTPContext = React.useContext(OTPInputContext);
  const { char, hasFakeCaret, isActive } = inputOTPContext.slots[index];

  return (
    <div
      ref={ref}
      className={`position-relative d-flex justify-content-center align-items-center border shadow-sm ${isActive ? "border-primary" : ""} ${className}`}
      style={{
        width: "2.25rem",
        height: "2.25rem",
        fontSize: "0.875rem",
        borderRadius: index === 0 ? ".25rem 0 0 .25rem" : index === inputOTPContext.slots.length - 1 ? "0 .25rem .25rem 0" : "0",
      }}
      {...props}
    >
      {char}
      {hasFakeCaret && (
        <div className="position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center">
          <div style={{ height: "1rem", width: "1px", backgroundColor: "black", animation: "caret-blink 1s step-end infinite" }} />
        </div>
      )}
    </div>
  );
});
InputOTPSlot.displayName = "InputOTPSlot";

const InputOTPSeparator = React.forwardRef((props, ref) => (
  <div ref={ref} role="separator" {...props}>
    <Minus />
  </div>
));
InputOTPSeparator.displayName = "InputOTPSeparator";

export { InputOTP, InputOTPGroup, InputOTPSlot, InputOTPSeparator };
