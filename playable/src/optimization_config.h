#ifndef DS_OPTIMIZATION_CONFIG_H
#define DS_OPTIMIZATION_CONFIG_H
#ifndef DS_P8_LOG_FIX
#define DS_P8_LOG_FIX 1
#endif
#ifndef DS_P8_HUD
#define DS_P8_HUD 0
#endif
#ifndef DS_P8_TRACK
#define DS_P8_TRACK 0
#endif
#ifndef DS_P8_MATRIXVIEWS
#define DS_P8_MATRIXVIEWS 0
#endif
#ifndef DS_P8_INTEGER
#define DS_P8_INTEGER 0
#endif
#ifndef DS_P8_CONST_TEX
#define DS_P8_CONST_TEX 0
#endif
#ifndef DS_P8_AUDIT_OPT
#define DS_P8_AUDIT_OPT 0
#endif
#ifndef DS_P8_CAPTURE_OPT
#define DS_P8_CAPTURE_OPT 0
#endif
/* Every optimization has a build-time rollback switch. */
#ifndef DS_OPT_MATRIX
#define DS_OPT_MATRIX 1
#endif
#ifndef DS_OPT_ATTRIBUTE
#define DS_OPT_ATTRIBUTE 1
#endif
#ifndef DS_RENDER_PROFILE
#define DS_RENDER_PROFILE 1
#endif
#ifndef DS_OPT_COPY
#define DS_OPT_COPY 1
#endif
#ifndef DS_OPT_PACK
#define DS_OPT_PACK 1
#endif
#ifndef DS_OPT_IDENTITY
#define DS_OPT_IDENTITY 1
#endif
#ifndef DS_OPT_STREAM
#define DS_OPT_STREAM 1
#endif
#ifndef DS_OPT_SPEEDUP
#define DS_OPT_SPEEDUP 1
#endif
#endif
