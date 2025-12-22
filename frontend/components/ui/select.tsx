"use client"

import * as React from "react"
import {
  Select as MuiSelect,
  MenuItem,
  FormControl,
} from '@mui/material'

// 兼容 Radix UI Select API 的包装组件
export interface SelectProps {
  value?: string
  onValueChange?: (value: string) => void
  disabled?: boolean
  children?: React.ReactNode
  className?: string
}

// 用于从 children 中提取选项
const extractOptions = (children: React.ReactNode): Array<{ value: string; label: React.ReactNode; disabled?: boolean }> => {
  const options: Array<{ value: string; label: React.ReactNode; disabled?: boolean }> = []
  
  const traverse = (node: React.ReactNode) => {
    React.Children.forEach(node, (child: any) => {
      if (!child) return
      
      if (child.type === SelectContent || child.type?.displayName === 'SelectContent') {
        traverse(child.props.children)
      } else if (child.type === SelectItem || child.type?.displayName === 'SelectItem') {
        options.push({
          value: child.props.value,
          label: child.props.children,
          disabled: child.props.disabled,
        })
      } else if (child.props?.children) {
        traverse(child.props.children)
      }
    })
  }
  
  traverse(children)
  return options
}

const Select = ({ value, onValueChange, disabled, children, className }: SelectProps) => {
  const options = React.useMemo(() => extractOptions(children), [children])

  const handleChange = (event: any) => {
    onValueChange?.(event.target.value)
  }

  return (
    <FormControl fullWidth size="small" className={className}>
      <MuiSelect
        value={value || ''}
        onChange={handleChange}
        disabled={disabled}
        displayEmpty
        sx={{
          borderRadius: '0.5rem',
        }}
      >
        {options.map((option, index) => (
          <MenuItem key={index} value={option.value} disabled={option.disabled}>
            {option.label}
          </MenuItem>
        ))}
      </MuiSelect>
    </FormControl>
  )
}
Select.displayName = "Select"

const SelectTrigger = ({ children, className, ...props }: any) => {
  return null // SelectTrigger 在 MUI 中不需要单独组件
}
SelectTrigger.displayName = "SelectTrigger"

const SelectContent = ({ children, ...props }: any) => {
  return <>{children}</>
}
SelectContent.displayName = "SelectContent"

const SelectItem = ({ children, value, disabled, ...props }: any) => {
  return <>{children}</>
}
SelectItem.displayName = "SelectItem"

const SelectValue = ({ placeholder, ...props }: any) => {
  return null // SelectValue 在 MUI 中由 Select 本身处理
}
SelectValue.displayName = "SelectValue"

const SelectGroup = ({ children, ...props }: any) => {
  return <>{children}</>
}
SelectGroup.displayName = "SelectGroup"

const SelectLabel = ({ children, ...props }: any) => {
  return null
}
SelectLabel.displayName = "SelectLabel"

const SelectSeparator = () => null
SelectSeparator.displayName = "SelectSeparator"

const SelectScrollUpButton = () => null
SelectScrollUpButton.displayName = "SelectScrollUpButton"

const SelectScrollDownButton = () => null
SelectScrollDownButton.displayName = "SelectScrollDownButton"

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectScrollUpButton,
  SelectScrollDownButton,
}
