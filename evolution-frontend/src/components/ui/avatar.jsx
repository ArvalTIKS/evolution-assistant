import * as React from "react";

const Avatar = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`d-flex align-items-center justify-content-center rounded-circle overflow-hidden ${className || ''}`}
    style={{ width: '40px', height: '40px' }}
    {...props}
  />
));
Avatar.displayName = "Avatar";

const AvatarImage = React.forwardRef(({ className, ...props }, ref) => (
  <img
    ref={ref}
    className={`img-fluid rounded-circle ${className || ''}`}
    {...props}
  />
));
AvatarImage.displayName = "AvatarImage";

const AvatarFallback = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`d-flex align-items-center justify-content-center rounded-circle bg-secondary text-white ${className || ''}`}
    style={{ width: '100%', height: '100%' }}
    {...props}
  />
));
AvatarFallback.displayName = "AvatarFallback";

export { Avatar, AvatarImage, AvatarFallback };