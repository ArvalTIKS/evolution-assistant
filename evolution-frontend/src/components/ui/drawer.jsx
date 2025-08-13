import * as React from "react";

const Drawer = ({ shouldScaleBackground = true, ...props }) => (
  <div {...props} />
);
Drawer.displayName = "Drawer";

const DrawerTrigger = ({ children, ...props }) => (
  <button type="button" data-bs-toggle="offcanvas" data-bs-target="#drawer" {...props}>
    {children}
  </button>
);

const DrawerPortal = ({ children }) => <>{children}</>;

const DrawerClose = ({ className, ...props }) => (
  <button
    type="button"
    className={`btn-close ${className || ''}`}
    data-bs-dismiss="offcanvas"
    aria-label="Close"
    {...props}
  />
);
DrawerClose.displayName = "DrawerClose";

const DrawerOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`offcanvas-backdrop fade ${className || ''}`}
    {...props}
  />
));
DrawerOverlay.displayName = "DrawerOverlay";

const DrawerContent = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={`offcanvas offcanvas-bottom rounded-top ${className || ''}`}
    id="drawer"
    tabIndex="-1"
    aria-labelledby="drawerLabel"
    {...props}
  >
    <div className="offcanvas-header">
      <div className="mx-auto mt-2 h-2 w-25 rounded-pill bg-secondary" />
      <DrawerClose className="position-absolute top-0 end-0 m-2" />
    </div>
    <div className="offcanvas-body">{children}</div>
  </div>
));
DrawerContent.displayName = "DrawerContent";

const DrawerHeader = ({ className, ...props }) => (
  <div className={`offcanvas-header text-center ${className || ''}`} {...props} />
);
DrawerHeader.displayName = "DrawerHeader";

const DrawerFooter = ({ className, ...props }) => (
  <div className={`offcanvas-body d-flex flex-column gap-2 ${className || ''}`} {...props} />
);
DrawerFooter.displayName = "DrawerFooter";

const DrawerTitle = React.forwardRef(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    className={`offcanvas-title ${className || ''}`}
    id="drawerLabel"
    {...props}
  />
));
DrawerTitle.displayName = "DrawerTitle";

const DrawerDescription = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`text-muted small ${className || ''}`}
    {...props}
  />
));
DrawerDescription.displayName = "DrawerDescription";

export {
  Drawer,
  DrawerPortal,
  DrawerOverlay,
  DrawerTrigger,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerFooter,
  DrawerTitle,
  DrawerDescription,
};