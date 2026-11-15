import type { ChangeEvent, CSSProperties, FC, KeyboardEvent, ReactNode } from "react";
import { COLORS } from "../src/ui/styles";

export const Router: { MainRunningApp?: { appid?: number | string } } = {};

export const Focusable: FC<{
  children?: ReactNode;
  style?: CSSProperties;
  className?: string;
  role?: string;
  tabIndex?: number;
  "aria-label"?: string;
  onActivate?: () => void;
  onClick?: () => void;
}> = ({
  children,
  style,
  className,
  role = "button",
  tabIndex = 0,
  "aria-label": ariaLabel,
  onActivate,
  onClick,
}) => {
  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (onActivate) {
        onActivate();
      } else {
        onClick?.();
      }
    }
  };
  return (
    <div
      role={role}
      tabIndex={tabIndex}
      aria-label={ariaLabel}
      className={className}
      style={style}
      onClick={() => onClick?.()}
      onKeyDown={handleKeyDown}
    >
      {children}
    </div>
  );
};

export interface SingleDropdownOption {
  data: unknown;
  label: ReactNode;
  options?: never;
}

export interface MultiDropdownOption {
  label: ReactNode;
  options: DropdownOption[];
  data?: never;
}

export type DropdownOption = SingleDropdownOption | MultiDropdownOption;

const sectionTitleStyle: CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  letterSpacing: "0.09em",
  textTransform: "uppercase",
  color: COLORS.textMuted,
  padding: "6px 2px 4px",
  borderBottom: "1px solid #2a2e35",
  marginBottom: "4px",
};

const rowStyle: CSSProperties = {
  padding: "3px 0",
  borderBottom: "none",
  width: "100%",
  boxSizing: "border-box",
};

export const PanelSection: FC<{ title?: string; children?: ReactNode }> = ({
  title,
  children,
}) => (
  <section style={{ marginBottom: "8px", width: "100%", boxSizing: "border-box" }}>
    {title && <div style={sectionTitleStyle}>{title}</div>}
    <div>{children}</div>
  </section>
);

export const PanelSectionRow: FC<{ children?: ReactNode }> = ({ children }) => (
  <div style={rowStyle}>{children}</div>
);

export const ToggleField: FC<{
  label?: ReactNode;
  description?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
}> = ({ label, description, checked, disabled, onChange }) => (
  <label
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "10px",
      padding: "6px 8px",
      borderRadius: "4px",
      background: "#1c1e22",
      border: "1px solid #292d34",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.6 : 1,
      boxSizing: "border-box",
      width: "100%",
    }}
  >
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: "12px", fontWeight: 600, color: COLORS.textPrimary }}>{label}</div>
      {description && (
        <div
          style={{
            fontSize: "10.5px",
            color: COLORS.textSecondary,
            lineHeight: 1.3,
            marginTop: "2px",
          }}
        >
          {description}
        </div>
      )}
    </div>
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange?.(e.target.checked)}
      style={{ display: "none" }}
    />
    <span
      aria-hidden="true"
      style={{
        width: "34px",
        height: "18px",
        boxSizing: "border-box",
        borderRadius: "3px",
        background: checked ? COLORS.accent : "#2a2e36",
        border: checked ? `1px solid ${COLORS.accentBright}` : "1px solid #3c414b",
        position: "relative",
        flexShrink: 0,
        transition: "background 120ms ease, border-color 120ms ease",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: "2px",
          left: checked ? "18px" : "2px",
          width: "12px",
          height: "12px",
          borderRadius: "2px",
          background: checked ? COLORS.accentInk : COLORS.textSecondary,
          transition: "left 120ms ease, background 120ms ease",
        }}
      />
    </span>
  </label>
);

export const ButtonItem: FC<{
  children?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  layout?: "below" | "inline";
  onClick?: (e: unknown) => void;
}> = ({ children, description, disabled, onClick }) => (
  <div style={{ width: "100%", boxSizing: "border-box" }}>
    <button
      type="button"
      disabled={disabled}
      onClick={(e) => onClick?.(e)}
      style={{
        width: "100%",
        boxSizing: "border-box",
        padding: "7px 10px",
        borderRadius: "4px",
        border: "1px solid #383d46",
        background: "#25282e",
        boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.04)",
        color: COLORS.textPrimary,
        fontSize: "12px",
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.6 : 1,
        textAlign: "center",
      }}
    >
      {children}
    </button>
    {description && (
      <div
        style={{
          fontSize: "10.5px",
          color: COLORS.textSecondary,
          marginTop: "3px",
          padding: "0 4px",
        }}
      >
        {description}
      </div>
    )}
  </div>
);

export const SliderField: FC<{
  label?: ReactNode;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  valueSuffix?: string;
  showValue?: boolean;
  disabled?: boolean;
  onChange?: (value: number) => void;
}> = ({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  valueSuffix = "",
  showValue = true,
  disabled,
  onChange,
}) => (
  <div
    style={{
      padding: "6px 8px",
      borderRadius: "4px",
      background: "#1c1e22",
      border: "1px solid #292d34",
      boxSizing: "border-box",
      width: "100%",
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: "4px",
      }}
    >
      <span style={{ fontSize: "12px", fontWeight: 600, color: COLORS.textPrimary }}>{label}</span>
      {showValue && (
        <span
          style={{
            fontFamily: COLORS.monoFont,
            fontSize: "11px",
            fontWeight: 700,
            color: COLORS.accentBright,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {value}
          {valueSuffix}
        </span>
      )}
    </div>
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange?.(Number(e.target.value))}
      style={{
        width: "100%",
        accentColor: COLORS.accent,
        cursor: disabled ? "not-allowed" : "pointer",
        margin: 0,
      }}
    />
  </div>
);

export const DropdownItem: FC<{
  label?: ReactNode;
  rgOptions: DropdownOption[];
  selectedOption: unknown;
  disabled?: boolean;
  onChange?: (option: SingleDropdownOption) => void;
}> = ({ label, rgOptions, selectedOption, disabled, onChange }) => {
  const flatOptions = rgOptions.filter((o): o is SingleDropdownOption => "data" in o);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "8px",
        padding: "6px 8px",
        borderRadius: "4px",
        background: "#1c1e22",
        border: "1px solid #292d34",
        boxSizing: "border-box",
        width: "100%",
      }}
    >
      <span
        style={{
          fontSize: "12px",
          fontWeight: 600,
          color: COLORS.textPrimary,
          flexShrink: 0,
        }}
      >
        {label}
      </span>
      <select
        disabled={disabled}
        value={String(selectedOption)}
        onChange={(e) => {
          const found = flatOptions.find((o) => String(o.data) === e.target.value);
          if (found) onChange?.(found);
        }}
        style={{
          maxWidth: "185px",
          minWidth: 0,
          flex: 1,
          padding: "5px 7px",
          borderRadius: "3px",
          border: "1px solid #383d46",
          background: COLORS.bgInput,
          color: COLORS.textPrimary,
          fontSize: "11px",
          fontWeight: 600,
        }}
      >
        {flatOptions.map((opt) => (
          <option key={String(opt.data)} value={String(opt.data)}>
            {String(opt.label)}
          </option>
        ))}
      </select>
    </div>
  );
};

export const TextField: FC<{
  label?: ReactNode;
  placeholder?: string;
  value?: string;
  disabled?: boolean;
  bIsPassword?: boolean;
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
}> = ({ label, placeholder, value = "", disabled, bIsPassword, onChange }) => (
  <div
    style={{
      padding: "6px 8px",
      borderRadius: "4px",
      background: "#1c1e22",
      border: "1px solid #292d34",
      boxSizing: "border-box",
      width: "100%",
    }}
  >
    {label && (
      <div
        style={{
          fontSize: "11px",
          fontWeight: 600,
          color: COLORS.textSecondary,
          marginBottom: "4px",
        }}
      >
        {label}
      </div>
    )}
    <input
      type={bIsPassword ? "password" : "text"}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={onChange}
      style={{
        width: "100%",
        boxSizing: "border-box",
        padding: "5px 8px",
        borderRadius: "3px",
        border: "1px solid #383d46",
        background: COLORS.bgInput,
        color: COLORS.textPrimary,
        fontSize: "11.5px",
        fontFamily: COLORS.monoFont,
      }}
    />
  </div>
);
