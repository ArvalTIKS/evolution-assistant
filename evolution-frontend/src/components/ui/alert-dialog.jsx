import * as React from "react";

const AlertDialog = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const AlertDialogTrigger = ({ children, ...props }) => (
  <button type="button" data-bs-toggle="modal" data-bs-target="#alertDialog" {...props}>
    {children}
  </button>
);

const AlertDialogPortal = ({ children }) => <>{children}</>;

const AlertDialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`modal-backdrop fade ${className || ''}`}
    {...props}
  />
));
AlertDialogOverlay.displayName = "AlertDialogOverlay";

const AlertDialogContent = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    className="modal fade"
    id="alertDialog"
    tabIndex="-1"
    aria-labelledby="alertDialogLabel"
    aria-hidden="true"
  >
    <div
      ref={ref}
      className={`modal-dialog modal-dialog-centered ${className || ''}`}
      {...props}
    >
      <div className="modal-content">{children}</div>
    </div>
  </div>
));
AlertDialogContent.displayName = "AlertDialogContent";

const AlertDialogHeader = ({ className, ...props }) => (
  <div className={`modal-header ${className || ''}`} {...props} />
);
AlertDialogHeader.displayName = "AlertDialogHeader";

const AlertDialogFooter = ({ className, ...props }) => (
  <div className={`modal-footer ${className || ''}`} {...props} />
);
AlertDialogFooter.displayName = "AlertDialogFooter";

const AlertDialogTitle = React.forwardRef(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    className={`modal-title ${className || ''}`}
    id="alertDialogLabel"
    {...props}
  />
));
AlertDialogTitle.displayName = "AlertDialogTitle";

const AlertDialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={`modal-body ${className || ''}`} {...props} />
));
AlertDialogDescription.displayName = "AlertDialogDescription";

const AlertDialogAction = React.forwardRef(({ className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    className={`btn btn-primary ${className || ''}`}
    data-bs-dismiss="modal"
    {...props}
  />
));
AlertDialogAction.displayName = "AlertDialogAction";

const AlertDialogCancel = React.forwardRef(({ className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    className={`btn btn-outline-secondary ${className || ''}`}
    data-bs-dismiss="modal"
    {...props}
  />
));
AlertDialogCancel.displayName = "AlertDialogCancel";

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
};