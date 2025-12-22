"use client"

import * as React from "react"
import { LinearProgress, LinearProgressProps } from '@mui/material'
import { cn } from "@/lib/utils"

export interface ProgressProps extends LinearProgressProps {
  value?: number
  className?: string
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, ...props }, ref) => {
    return (
      <LinearProgress
        ref={ref}
        variant="determinate"
        value={value}
        className={cn("h-2.5 rounded-full", className)}
        sx={{
          backgroundColor: 'rgba(0, 0, 0, 0.1)',
          '& .MuiLinearProgress-bar': {
            backgroundColor: '#6366f1', // indigo-600
            borderRadius: '9999px',
          },
          ...props.sx,
        }}
        {...props}
      />
    )
  }
)
Progress.displayName = "Progress"

export { Progress }
