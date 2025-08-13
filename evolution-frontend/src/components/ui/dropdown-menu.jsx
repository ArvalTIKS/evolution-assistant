import * as React from "react";
import { Check, ChevronRight, Circle } from "lucide-react";

const DropdownMenu = ({ children, ...props }) => (
  <div className="dropdown" {...props}>{children}</div>
);

const DropdownMenuTrigger = ({ children, ...props }) => (
  <button className="dropdown-toggle" data-bs-toggle="dropdown" {...props}>
    {children}
  </button>
);

const DropdownMenuGroup = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const DropdownMenuPortal = ({ children }) => <>{children}</>;

const DropdownMenuSub = ({ children, ...props }) => (
  <div className="dropdown-submenu" {...props}>{children}</div>
);

const DropdownMenuRadioGroup = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

const DropdownMenuSubTrigger = React.forwardRef(({ className, inset, children, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item d-flex align-items-center gap-2 ${inset ? "ps-5" : ""} ${className || ''}`}
    {...props}
  >
    {children}
    <ChevronRight className="ms-auto h-4 w-4" />
  </div>
));
DropdownMenuSubTrigger.displayName = "DropdownMenuSubTrigger";

const DropdownMenuSubContent = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-menu shadow-sm ${className || ''}`}
    {...props}
  />
));
DropdownMenuSubContent.displayName = "DropdownMenuSubContent";

const DropdownMenuContent = React.forwardRef(({ className, sideOffset = 4, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-menu shadow-sm overflow-y-auto ${className || ''}`}
    style={{ minWidth: '8rem', maxHeight: 'var(--radix-dropdown-menu-content-available-height)', marginTop: sideOffset }}
    {...props}
  />
));
DropdownMenuContent.displayName = "DropdownMenuContent";

const DropdownMenuItem = React.forwardRef(({ className, inset, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item d-flex align-items-center gap-2 ${inset ? "ps-5" : ""} ${className || ''}`}
    {...props}
  />
));
DropdownMenuItem.displayName = "DropdownMenuItem";

const DropdownMenuCheckboxItem = React.forwardRef(({ className, children, checked, ...props }, ref) => (
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
DropdownMenuCheckboxItem.displayName = "DropdownMenuCheckboxItem";

const DropdownMenuRadioItem = React.forwardRef(({ className, children, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-item d-flex align-items-center ${className || ''}`}
    {...props}
  >
    <span className="d-flex align-items-center justify-content-center me-2" style={{ width: '1.5rem' }}>
      <Circle className="h-2 w-2" />
    </span>
    {children}
  </div>
));
DropdownMenuRadioItem.displayName = "DropdownMenuRadioItem";

const DropdownMenuLabel = React.forwardRef(({ className, inset, ...props }, ref) => (
  <div
    ref={ref}
    className={`dropdown-header fw-bold ${inset ? "ps-5" : ""} ${className || ''}`}
    {...props}
  />
));
DropdownMenuLabel.displayName = "DropdownMenuLabel";

const DropdownMenuSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <hr
    ref={ref}
    className={`dropdown-divider my-1 ${className || ''}`}
    {...props}
  />
));
DropdownMenuSeparator.displayName = "DropdownMenuSeparator";

const DropdownMenuShortcut = ({ className, ...props }) => (
  <span
    className={`ms-auto text-muted small ${className || ''}`}
    {...props}
  />
);
DropdownMenuShortcut.displayName = "DropdownMenuShortcut";

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuGroup,
  DropdownMenuPortal,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuRadioGroup,
};