import * as React from "react";
import { Check, ChevronRight, Circle } from "lucide-react";

const ContextMenu = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const ContextMenuTrigger = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const ContextMenuGroup = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const ContextMenuPortal = ({ children }) => <>{children}</>;

const ContextMenuSub = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const ContextMenuRadioGroup = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const ContextMenuSubTrigger = React.forwardRef(({ className, inset, children, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item d-flex align-items-center ${inset ? "ps-5" : ""} ${className || ''}`}
    {...props}
  >
    {children}
    <ChevronRight className="ms-auto h-4 w-4" />
  </div>
));
ContextMenuSubTrigger.displayName = "ContextMenuSubTrigger";

const ContextMenuSubContent = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-menu shadow-sm ${className || ''}`}
    {...props}
  />
));
ContextMenuSubContent.displayName = "ContextMenuSubContent";

const ContextMenuContent = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-menu shadow-sm overflow-y-auto ${className || ''}`}
    style={{ minWidth: '8rem', maxHeight: 'var(--radix-context-menu-content-available-height)' }}
    {...props}
  />
));
ContextMenuContent.displayName = "ContextMenuContent";

const ContextMenuItem = React.forwardRef(({ className, inset, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item ${inset ? "ps-5" : ""} ${className || ''}`}
    {...props}
  />
));
ContextMenuItem.displayName = "ContextMenuItem";

const ContextMenuCheckboxItem = React.forwardRef(({ className, children, checked, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item d-flex align-items-center ${className || ''}`}
    {...props}
  >
    <span className="d-flex align-items-center justify-content-center me-2" style={{ width: '1.5rem' }}>
      {checked && <Check className="h-4 w-4" />}
    </span>
    {children}
  </div>
));
ContextMenuCheckboxItem.displayName = "ContextMenuCheckboxItem";

const ContextMenuRadioItem = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item d-flex align-items-center ${className || ''}`}
    {...props}
  >
    <span className="d-flex align-items-center justify-content-center me-2" style={{ width: '1.5rem' }}>
      <Circle className="h-4 w-4" />
    </span>
    {children}
  </div>
));
ContextMenuRadioItem.displayName = "ContextMenuRadioItem";

const ContextMenuLabel = React.forwardRef(({ className, inset, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-header fw-bold ${inset ? "ps-5" : ""} ${className || ''}`}
    {...props}
  />
));
ContextMenuLabel.displayName = "ContextMenuLabel";

const ContextMenuSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <hr
    ref={ref}
    className={`dropdown-divider my-1 ${className || ''}`}
    {...props}
  />
));
ContextMenuSeparator.displayName = "ContextMenuSeparator";

const ContextMenuShortcut = ({ className, ...props }) => (
  <span
    className={`ms-auto text-muted small ${className || ''}`}
    {...props}
  />
);
ContextMenuShortcut.displayName = "ContextMenuShortcut";

export {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuCheckboxItem,
  ContextMenuRadioItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuGroup,
  ContextMenuPortal,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuRadioGroup,
};