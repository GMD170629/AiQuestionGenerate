"use client"

import * as React from "react"
import { TextField, TextFieldProps } from '@mui/material'

export interface TextareaProps extends Omit<TextFieldProps, 'multiline'> {
  rows?: number
  className?: string
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, rows = 3, ...props }, ref) => {
    return (
      <TextField
        inputRef={ref}
        variant="outlined"
        multiline
        rows={rows}
        fullWidth
        {...props}
        sx={{
          ...props.sx,
        }}
      />
    )
  }
)
Textarea.displayName = "Textarea"

export { Textarea }
