import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { buttonVariants } from "./button";

function Calendar({ className, classNames, showOutsideDays = true, ...props }) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={`p-3 ${className || ''}`}
      classNames={{
        months: "d-flex flex-column flex-sm-row gap-4",
        month: "d-flex flex-column gap-4",
        caption: "d-flex justify-content-center pt-1 position-relative align-items-center",
        caption_label: "fw-medium",
        nav: "d-flex gap-1 align-items-center",
        nav_button: `${buttonVariants({ variant: "outline" })} btn-sm p-0 opacity-50 hover-opacity-100`,
        nav_button_previous: "position-absolute start-0",
        nav_button_next: "position-absolute end-0",
        table: "w-100 border-collapse",
        head_row: "d-flex",
        head_cell: "text-muted w-8 fw-normal fs-6",
        row: "d-flex w-100 mt-2",
        cell: `text-center position-relative ${props.mode === "range" ? "has-selected-range" : "has-selected"}`,
        day: `${buttonVariants({ variant: "ghost" })} w-8 h-8 p-0 fw-normal aria-selected-opacity-100`,
        day_range_start: "day-range-start",
        day_range_end: "day-range-end",
        day_selected: "bg-primary text-white hover-bg-primary hover-text-white",
        day_today: "bg-light text-dark",
        day_outside: "text-muted opacity-50",
        day_disabled: "text-muted opacity-50",
        day_range_middle: "bg-light text-dark",
        day_hidden: "invisible",
        ...classNames,
      }}
      components={{
        IconLeft: ({ className, ...props }) => (
          <ChevronLeft className={`h-4 w-4 ${className || ''}`} {...props} />
        ),
        IconRight: ({ className, ...props }) => (
          <ChevronRight className={`h-4 w-4 ${className || ''}`} {...props} />
        ),
      }}
      {...props}
    />
  );
}
Calendar.displayName = "Calendar";

export { Calendar };