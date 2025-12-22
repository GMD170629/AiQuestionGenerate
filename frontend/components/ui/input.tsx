"use client"

import * as React from "react"
import { TextField, TextFieldProps } from '@mui/material'

export interface InputProps extends Omit<TextFieldProps, 'multiline' | 'rows'> {
  asChild?: boolean
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <TextField
        inputRef={ref}
        variant="outlined"
        size="small"
        fullWidth
        {...props}
        sx={{
          ...props.sx,
        }}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
