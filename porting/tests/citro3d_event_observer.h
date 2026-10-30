#ifndef CITRO3D_EVENT_OBSERVER_H
#define CITRO3D_EVENT_OBSERVER_H
#include <3ds.h>
#include <stdio.h>
#define CLEAR_EVENTS_VERSION "0.1.1"
#define CLEAR_EVENTS_ROOT "sdmc:/3ds/citro3d-control-v" CLEAR_EVENTS_VERSION "/"
void clear_events_install(FILE *logfile);
void clear_events_remove(void);
void clear_events_track(gxCmdQueue_s *queue);
int clear_events_checkpoint(const char *label);
int clear_events_changed(void);
const char *clear_events_last_file(void);
#ifdef CLEAR_EVENTS_FAULT
int clear_events_software_selfcheck(void);
#endif
#endif
