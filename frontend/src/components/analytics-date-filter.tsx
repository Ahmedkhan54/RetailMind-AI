"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type AnalyticsDateFilterProps = {
  dateFrom: string;
  dateTo: string;
  disabled?: boolean;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
  onClear: () => void;
};

function toDateInputValue(value: Date) {
  return value.toISOString().slice(0, 10);
}

export function AnalyticsDateFilter({
  dateFrom,
  dateTo,
  disabled = false,
  onDateFromChange,
  onDateToChange,
  onClear,
}: AnalyticsDateFilterProps) {
  const invalidRange = Boolean(dateFrom && dateTo && dateFrom > dateTo);

  function setLast30Days() {
    const end = new Date();
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - 29);
    onDateFromChange(toDateInputValue(start));
    onDateToChange(toDateInputValue(end));
  }

  return (
    <div className="analytics-date-filter" aria-label="Filter analytics by date">
      <label className="analytics-date-field">
        <span>From date</span>
        <Input
          type="date"
          value={dateFrom}
          disabled={disabled}
          aria-label="Analytics start date"
          aria-invalid={invalidRange}
          onChange={(event) => onDateFromChange(event.target.value)}
        />
      </label>
      <label className="analytics-date-field">
        <span>To date</span>
        <Input
          type="date"
          value={dateTo}
          disabled={disabled}
          aria-label="Analytics end date"
          aria-invalid={invalidRange}
          onChange={(event) => onDateToChange(event.target.value)}
        />
      </label>
      <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={setLast30Days}>
        Last 30 days
      </Button>
      <Button type="button" variant="ghost" size="sm" disabled={disabled || (!dateFrom && !dateTo)} onClick={onClear}>
        Clear dates
      </Button>
      {invalidRange ? <p className="analytics-date-error" role="alert">The start date must be on or before the end date.</p> : null}
    </div>
  );
}
