import * as React from "react";
import { X } from "lucide-react";

const Dialog = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const DialogTrigger = ({ children, ...props }) => (
  <button type="button" data-bs-toggle="modal" data-bs-target="#dialog" {...props}>
    {children}
  </button>
);

const DialogPortal = ({ children }) => <>{children}</>;

const DialogClose = React.forwardRef(({ className, ...props }, ref) => (
  <button
    ref={ref}
    type="button"
    className={`btn-close ${className || ''}`}
    data-bs-dismiss="modal"
    aria-label="Close"
    {...props}
  />
));
DialogClose.displayName = "DialogClose";

const DialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`modal-backdrop fade ${className || ''}`}
    {...props}
  />
));
DialogOverlay.displayName = "DialogOverlay";

const DialogContent = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    className="modal fade"
    id="dialog"
    tabIndex="-1"
    aria-labelledby="dialogLabel"
    aria-hidden="true"
  >
    <div
      ref={ref}
      className={`modal-dialog modal-dialog-centered ${className || ''}`}
      {...props}
    >
      <div className="modal-content">
        {children}
        <DialogClose className="position-absolute top-0 end-0 m-2" />
      </div>
    </div>
  </div>
));
DialogContent.displayName = "DialogContent";

const DialogHeader = ({ className, ...props }) => (
  <div className={`modal-header ${className || ''}`} {...props} />
);
DialogHeader.displayName = "DialogHeader";

const DialogFooter = ({ className, ...props }) => (
  <div className={`modal-footer ${className || ''}`} {...props} />
);
DialogFooter.displayName = "DialogFooter";

const DialogTitle = React.forwardRef(({ className, ...props }, ref) => (
  <h5
    ref={ref}
    className={`modal-title ${className || ''}`}
    id="dialogLabel"
    {...props}
  />
));
DialogTitle.displayName = "DialogTitle";

const DialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`modal-body ${className || ''}`}
    {...props}
  />
));
DialogDescription.displayName = "DialogDescription";

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
};