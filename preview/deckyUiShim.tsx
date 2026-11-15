import type { ChangeEvent, CSSProperties, FC, ReactNode } from "react";
import { COLORS } from "../src/ui/styles";

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
  fontSize: "10.5px",
  fontWeight: 700,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: COLORS.textSecondary,
  padding: "6px 2px 4px",
  borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
  marginBottom: "3px",
};

const rowStyle: CSSProperties = {
  padding: "4px 0",
  borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
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
      padding: "5px 8px",
      borderRadius: "7px",
      background: "rgba(255, 255, 255, 0.025)",
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
        width: "36px",
        height: "20px",
        borderRadius: "999px",
        background: checked ? COLORS.neonBlue : "rgba(148, 163, 184, 0.28)",
        position: "relative",
        flexShrink: 0,
        transition: "background 120ms ease",
        boxShadow: checked ? "0 0 10px rgba(0, 195, 227, 0.35)" : "inset 0 1px 2px rgba(0,0,0,0.4)",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: "2px",
          left: checked ? "18px" : "2px",
          width: "16px",
          height: "16px",
          borderRadius: "50%",
          background: "#ffffff",
          boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
          transition: "left 120ms ease",
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
        borderRadius: "7px",
        border: "1px solid rgba(255, 255, 255, 0.12)",
        background: "linear-gradient(180deg, #253140 0%, #1d2734 100%)",
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
      padding: "5px 8px",
      borderRadius: "7px",
      background: "rgba(255, 255, 255, 0.025)",
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
        <span style={{ fontSize: "11.5px", fontWeight: 700, color: COLORS.neonBlue }}>
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
        accentColor: COLORS.neonBlue,
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
        padding: "5px 8px",
        borderRadius: "7px",
        background: "rgba(255, 255, 255, 0.025)",
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
          borderRadius: "6px",
          border: "1px solid rgba(255, 255, 255, 0.14)",
          background: "#212b38",
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
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
}> = ({ label, placeholder, value = "", disabled, onChange }) => (
  <div
    style={{
      padding: "5px 8px",
      borderRadius: "7px",
      background: "rgba(255, 255, 255, 0.025)",
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
      type="text"
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      onChange={onChange}
      style={{
        width: "100%",
        boxSizing: "border-box",
        padding: "5px 8px",
        borderRadius: "6px",
        border: "1px solid rgba(255, 255, 255, 0.14)",
        background: "#0d131a",
        color: COLORS.textPrimary,
        fontSize: "11.5px",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      }}
    />
  </div>
);
