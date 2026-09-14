'use client'

import { Children, isValidElement, type ReactNode } from 'react'
import { Select } from '@base-ui/react/select'
import { Check, ChevronDown } from 'lucide-react'
import { useUiVariant } from '@/lib/ui-variant'

/** Canopy v15 menu materials on the app's existing accessible primitive. */
export function ChoiceSelect({ children, value, onChange, disabled, name, id, className = '', 'aria-label': label }: {
  children: ReactNode; value: string; onChange: (event: { target: { value: string } }) => void
  disabled?: boolean; name?: string; id?: string; className?: string; 'aria-label'?: string
}) {
  const { variant } = useUiVariant()
  const options = Children.toArray(children).filter(isValidElement<{ value: string; children: ReactNode; disabled?: boolean }>).map(child => ({ value: child.props.value, label: child.props.children, disabled: child.props.disabled }))
  if (variant !== 'canopy') return <select value={value} onChange={onChange} disabled={disabled} name={name} id={id} className={className} aria-label={label}>{children}</select>
  return <Select.Root value={value} items={options} onValueChange={next => { if (next !== null) onChange({ target: { value: next } }) }} disabled={disabled} name={name}>
    <Select.Trigger id={id} aria-label={label} className={`cp-choice-trigger ${className}`}><Select.Value /><ChevronDown size={14} /></Select.Trigger>
    <Select.Portal>
      <Select.Positioner sideOffset={6} collisionPadding={12} alignItemWithTrigger={false} className="cp-choice-positioner">
        <Select.Popup className="cp-choice-menu" onKeyDown={event => { if (event.key === 'Escape') event.stopPropagation() }}>
          <Select.List>{options.map(option => <Select.Item className="cp-choice-option" key={option.value} value={option.value} disabled={option.disabled}><Select.ItemText>{option.label}</Select.ItemText><Select.ItemIndicator><Check size={15} /></Select.ItemIndicator></Select.Item>)}</Select.List>
        </Select.Popup>
      </Select.Positioner>
    </Select.Portal>
  </Select.Root>
}
