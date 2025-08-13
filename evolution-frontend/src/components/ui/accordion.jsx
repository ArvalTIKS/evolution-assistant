import * as React from "react";
import { ChevronDown } from "lucide-react";

const Accordion = ({ children, className, ...props }) => (
  <div className={`accordion ${className || ''}`} {...props}>
    {children}
  </div>
);

const AccordionItem = React.forwardRef(({ className, children, ...props }, ref) => (
  <div ref={ref} className={`accordion-item ${className || ''}`} {...props}>
    {children}
  </div>
));
AccordionItem.displayName = "AccordionItem";

const AccordionTrigger = React.forwardRef(({ className, children, ...props }, ref) => {
  const { id } = props;
  return (
    <h2 className="mb-0">
      <button
        ref={ref}
        className={`accordion-button collapsed d-flex align-items-center justify-content-between w-100 py-3 px-4 text-start ${className || ''}`}
        type="button"
        data-bs-toggle="collapse"
        data-bs-target={`#collapse-${id}`}
        aria-expanded="false"
        aria-controls={`collapse-${id}`}
        {...props}
      >
        {children}
        <ChevronDown className="h-4 w-4 ms-2" />
      </button>
    </h2>
  );
});
AccordionTrigger.displayName = "AccordionTrigger";

const AccordionContent = React.forwardRef(({ className, children, id, ...props }, ref) => (
  <div
    ref={ref}
    id={`collapse-${id}`}
    className={`accordion-collapse collapse ${className || ''}`}
    {...props}
  >
    <div className="accordion-body py-3 px-4">{children}</div>
  </div>
));
AccordionContent.displayName = "AccordionContent";

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent };