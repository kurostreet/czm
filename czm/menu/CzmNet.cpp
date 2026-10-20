/*
CzmNet.cpp - Counter Zombie Mobile: network for the menu through the Android side
Copyright (C) 2026 Counter Zombie Mobile authors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "extdll_menu.h"
#include "BaseMenu.h"
#include "CzmMenu.h"

/*
The menu has no HTTPS of its own. Android does it: CzmNet.java runs the requests on
its threads, the menu starts them and asks for the answers every frame. The calls go
through JNI with the JNIEnv of the game thread, which SDL gives out.
Every call keeps its JNI references in a local frame: the game thread never returns
to Java, references left behind would pile up.
On other systems there is no network for the menu, the online parts stay hidden.
*/
#ifdef __ANDROID__
#include <jni.h>
#include <dlfcn.h>

static JNIEnv *CZM_Env( void )
{
	typedef void *( *GetEnvFn )( void );
	static GetEnvFn getEnv;
	static bool tried;

	if( !tried )
	{
		void *sdl;

		tried = true;
		sdl = dlopen( "libSDL2.so", RTLD_NOW | RTLD_NOLOAD );
		if( !sdl )
			sdl = dlopen( "libSDL2.so", RTLD_NOW );
		if( sdl )
			getEnv = (GetEnvFn)dlsym( sdl, "SDL_AndroidGetJNIEnv" );
	}

	return getEnv ? (JNIEnv *)getEnv() : NULL;
}

static jclass CZM_NetClass( JNIEnv *env )
{
	static jclass cls;
	static bool failed;
	jclass local;

	if( cls || failed )
		return cls;

	local = env->FindClass( "ru/kurostreet/counterzombiemobile/CzmNet" );
	if( !local || env->ExceptionCheck( ))
	{
		env->ExceptionClear();
		failed = true;
		return NULL;
	}

	cls = (jclass)env->NewGlobalRef( local );
	env->DeleteLocalRef( local );
	return cls;
}

// a static method of CzmNet, NULL (and no exception left) if it is missing
static jmethodID CZM_Method( JNIEnv *env, jclass cls, const char *name, const char *sig )
{
	jmethodID id = env->GetStaticMethodID( cls, name, sig );

	if( env->ExceptionCheck( ))
	{
		env->ExceptionClear();
		return NULL;
	}
	return id;
}

static bool CZM_Begin( JNIEnv **env, jclass *cls )
{
	*env = CZM_Env();
	if( !*env )
		return false;
	*cls = CZM_NetClass( *env );
	if( !*cls )
		return false;
	return ( *env )->PushLocalFrame( 16 ) == 0;
}

static void CZM_End( JNIEnv *env )
{
	if( env->ExceptionCheck( ))
		env->ExceptionClear();
	env->PopLocalFrame( NULL );
}

static jbyteArray CZM_Bytes( JNIEnv *env, const char *text )
{
	jsize len = text ? (jsize)strlen( text ) : 0;
	jbyteArray array = env->NewByteArray( len );

	if( array && len )
		env->SetByteArrayRegion( array, 0, len, (const jbyte *)text );
	return array;
}

static void CZM_CopyString( JNIEnv *env, jstring str, char *out, size_t size )
{
	const char *chars;

	out[0] = 0;
	if( !str )
		return;
	chars = env->GetStringUTFChars( str, NULL );
	if( chars )
	{
		Q_strncpy( out, chars, size );
		env->ReleaseStringUTFChars( str, chars );
	}
}

bool CZM_NetAvailable( void )
{
	JNIEnv *env = CZM_Env();
	return env && CZM_NetClass( env );
}

bool CZM_CopyText( const char *text )
{
	JNIEnv *env; jclass cls;
	if( !CZM_Begin( &env, &cls )) return false;
	jmethodID m = CZM_Method( env, cls, "copyText", "(Ljava/lang/String;)Z" );
	bool copied = m && env->CallStaticBooleanMethod( cls, m, env->NewStringUTF( text ? text : "" ));
	CZM_End( env ); return copied;
}

void CZM_ServerAuthShow( const char *address, const char *name )
{
	JNIEnv *env;
	jclass cls;
	if( !CZM_Begin( &env, &cls )) return;
	jmethodID m = CZM_Method( env, cls, "serverAuthShow", "(Ljava/lang/String;Ljava/lang/String;Z)V" );
	if( m ) env->CallStaticVoidMethod( cls, m, env->NewStringUTF( address ), env->NewStringUTF( name ), (jboolean)CZM_IsRussian() );
	CZM_End( env );
}

static void CZM_AccountAction( const char *method, const char *key, const char *nick )
{
	JNIEnv *env;
	jclass cls;
	if( !CZM_Begin( &env, &cls )) return;
	jmethodID m = CZM_Method( env, cls, method, "(Ljava/lang/String;Ljava/lang/String;Z)V" );
	if( m ) env->CallStaticVoidMethod( cls, m, env->NewStringUTF( key ), env->NewStringUTF( nick ), (jboolean)CZM_IsRussian() );
	CZM_End( env );
}

void CZM_AccountShow( const char *key, const char *nick ) { CZM_AccountAction( "accountShow", key, nick ); }
void CZM_AccountRegister( const char *key, const char *nick ) { CZM_AccountAction( "accountRegister", key, nick ); }
void CZM_AccountContext( const char *key, const char *nick ) { CZM_AccountAction( "accountContext", key, nick ); }
void CZM_DistributionShow( const char *key, const char *nick ) { CZM_AccountAction( "distributionShow", key, nick ); }
void CZM_DistributionHelp( const char *key, const char *nick ) { CZM_AccountAction( "distributionHelp", key, nick ); }
bool CZM_DistributionChanged( void )
{
	JNIEnv *env; jclass cls;
	if( !CZM_Begin( &env, &cls )) return false;
	jmethodID m = CZM_Method( env, cls, "distributionChanged", "()Z" );
	bool changed = m && env->CallStaticBooleanMethod( cls, m ) != JNI_FALSE;
	CZM_End( env ); return changed;
}

bool CZM_AccountEvent( CUtlString &body )
{
	JNIEnv *env;
	jclass cls;
	bool found = false;
	if( !CZM_Begin( &env, &cls )) return false;
	jmethodID m = CZM_Method( env, cls, "accountEvent", "()[B" );
	jbyteArray result = m ? (jbyteArray)env->CallStaticObjectMethod( cls, m ) : NULL;
	if( result )
	{
		jsize n = env->GetArrayLength( result );
		if( n > 0 && n < 4096 )
		{
			char value[4096];
			env->GetByteArrayRegion( result, 0, n, (jbyte *)value ); value[n] = 0;
			body.Set( value ); found = true;
		}
	}
	CZM_End( env );
	return found;
}

void CZM_LayoutsShow( void ) { JNIEnv *env;jclass cls;if(!CZM_Begin(&env,&cls))return;jmethodID m=CZM_Method(env,cls,"layoutsShow","()V");if(m)env->CallStaticVoidMethod(cls,m);CZM_End(env); }


bool CZM_WidgetEvent( CUtlString &body )
{
	JNIEnv *env;
	jclass cls;
	bool found = false;
	if( !CZM_Begin( &env, &cls )) return false;
	jmethodID m = CZM_Method( env, cls, "widgetEvent", "()[B" );
	jbyteArray result = m ? (jbyteArray)env->CallStaticObjectMethod( cls, m ) : NULL;
	if( result )
	{
		jsize n = env->GetArrayLength( result );
		if( n > 0 && n < 256 )
		{
			char value[4096];
			env->GetByteArrayRegion( result, 0, n, (jbyte *)value ); value[n] = 0;
			body.Set( value ); found = true;
		}
	}
	CZM_End( env );
	return found;
}

bool CZM_CloudEvent( CUtlString &body )
{
	JNIEnv *env;
	jclass cls;
	bool found = false;
	if( !CZM_Begin( &env, &cls )) return false;
	jmethodID m = CZM_Method( env, cls, "cloudEvent", "()[B" );
	jbyteArray result = m ? (jbyteArray)env->CallStaticObjectMethod( cls, m ) : NULL;
	if( result )
	{
		jsize n = env->GetArrayLength( result );
		if( n > 0 && n < 262144 )
		{
			char *value=(char *)malloc(n+1);
            if(!value){CZM_End(env);return false;}
			env->GetByteArrayRegion( result, 0, n, (jbyte *)value ); value[n] = 0;
			body.Set( value ); free(value); found = true;
		}
	}
	CZM_End( env );
	return found;
}
void CZM_CloudApplied( int request, bool success ) {
 JNIEnv *env;jclass cls;if(!CZM_Begin(&env,&cls))return;
 jmethodID m=CZM_Method(env,cls,"cloudApplied","(IZ)V");if(m)env->CallStaticVoidMethod(cls,m,(jint)request,(jboolean)success);CZM_End(env);
}


void CZM_ColorPickerShow( int r, int g, int b )
{
	JNIEnv *env;
	jclass cls;
	if( !CZM_Begin( &env, &cls )) return;
	jmethodID m = CZM_Method( env, cls, "colorShow", "(IIIZ)V" );
	if( m ) env->CallStaticVoidMethod( cls, m, (jint)r, (jint)g, (jint)b, (jboolean)CZM_IsRussian() );
	CZM_End( env );
}

bool CZM_ColorPickerEvent( int &r, int &g, int &b )
{
	JNIEnv *env;
	jclass cls;
	bool found = false;
	if( !CZM_Begin( &env, &cls )) return false;
	jmethodID m = CZM_Method( env, cls, "colorEvent", "()[B" );
	jbyteArray result = m ? (jbyteArray)env->CallStaticObjectMethod( cls, m ) : NULL;
	if( result )
	{
		jsize n = env->GetArrayLength( result );
		if( n > 0 && n < 32 )
		{
			char value[32], tail;
			env->GetByteArrayRegion( result, 0, n, (jbyte *)value ); value[n] = 0;
			found = sscanf( value, "%d %d %d %c", &r, &g, &b, &tail ) == 3
				&& r >= 0 && r <= 255 && g >= 0 && g <= 255 && b >= 0 && b <= 255;
		}
	}
	CZM_End( env );
	return found;
}

void CZM_StartupReady( void )
{
	static bool sent;
	JNIEnv *env;
	jclass cls;
	if( sent || !CZM_Begin( &env, &cls )) return;
	jmethodID m = CZM_Method( env, cls, "startupReady", "()V" );
	if( m )
	{
		env->CallStaticVoidMethod( cls, m );
		sent = !env->ExceptionCheck();
	}
	CZM_End( env );
}

int CZM_NetRequest( const char *method, const char *url, const char *key, const char *body )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;
	int id = 0;

	if( !CZM_Begin( &env, &cls ))
		return 0;

	m = CZM_Method( env, cls, "request", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;[B)I" );
	if( m )
		id = env->CallStaticIntMethod( cls, m, env->NewStringUTF( method ), env->NewStringUTF( url ), env->NewStringUTF( key ? key : "" ),
			CZM_Bytes( env, body ));
	CZM_End( env );
	return id;
}

int CZM_NetUpload( const char *url, const char *key, const char *path, const char *contentType )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;
	int id = 0;

	if( !CZM_Begin( &env, &cls ))
		return 0;

	m = CZM_Method( env, cls, "upload", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)I" );
	if( m )
		id = env->CallStaticIntMethod( cls, m, env->NewStringUTF( url ), env->NewStringUTF( key ? key : "" ), env->NewStringUTF( path ),
			env->NewStringUTF( contentType ));
	CZM_End( env );
	return id;
}

int CZM_NetDownload( const char *url, const char *path )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;
	int id = 0;

	if( !CZM_Begin( &env, &cls ))
		return 0;

	m = CZM_Method( env, cls, "download", "(Ljava/lang/String;Ljava/lang/String;)I" );
	if( m )
		id = env->CallStaticIntMethod( cls, m, env->NewStringUTF( url ), env->NewStringUTF( path ));
	CZM_End( env );
	return id;
}

bool CZM_NetPoll( int id, int *status, CUtlString &body )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;
	jbyteArray result;
	bool done = false;

	if( id <= 0 || !CZM_Begin( &env, &cls ))
	{
		// nothing can come: report a network failure
		*status = 0;
		body.Clear();
		return true;
	}

	m = CZM_Method( env, cls, "poll", "(I)[B" );
	result = m ? (jbyteArray)env->CallStaticObjectMethod( cls, m, (jint)id ) : NULL;
	if( result )
	{
		jsize len = env->GetArrayLength( result );
		char *text = (char *)malloc( len + 1 );

		if( text )
		{
			char *newline;

			env->GetByteArrayRegion( result, 0, len, (jbyte *)text );
			text[len] = 0;
			*status = atoi( text );
			newline = strchr( text, '\n' );
			body.Set( newline ? newline + 1 : "" );
			free( text );
			done = true;
		}
	}
	CZM_End( env );
	return done;
}

static void CZM_CallString( const char *name, char *out, size_t size )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;

	out[0] = 0;
	if( !CZM_Begin( &env, &cls ))
		return;

	m = CZM_Method( env, cls, name, "()Ljava/lang/String;" );
	if( m )
		CZM_CopyString( env, (jstring)env->CallStaticObjectMethod( cls, m ), out, size );
	CZM_End( env );
}

const char *CZM_NetDeviceId( void )
{
	static char id[96];
	static bool done;

	if( !done )
	{
		CZM_CallString( "deviceId", id, sizeof( id ));
		done = true;
	}
	return id;
}

void CZM_NetNewKey( char *out, size_t size )
{
	CZM_CallString( "newKey", out, size );
}

int CZM_NetVersionCode( void )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;
	int code = 0;

	if( !CZM_Begin( &env, &cls ))
		return 0;
	m = CZM_Method( env, cls, "versionCode", "()I" );
	if( m )
		code = env->CallStaticIntMethod( cls, m );
	CZM_End( env );
	return code;
}

bool CZM_NetCanSelfUpdate( void )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;
	bool can = false;

	if( !CZM_Begin( &env, &cls ))
		return false;
	m = CZM_Method( env, cls, "canSelfUpdate", "()Z" );
	if( m )
		can = env->CallStaticBooleanMethod( cls, m ) != JNI_FALSE;
	CZM_End( env );
	return can;
}

void CZM_UpdateStart( const CzmUpdateInfo &update )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;

	if( !CZM_Begin( &env, &cls ))
		return;
	m = CZM_Method( env, cls, "updateStart", "(Ljava/lang/String;Ljava/lang/String;JLjava/lang/String;Ljava/lang/String;JLjava/lang/String;)V" );
	if( m )
		env->CallStaticVoidMethod( cls, m, env->NewStringUTF( update.url ), env->NewStringUTF( update.sha256 ), (jlong)update.size,
			env->NewStringUTF( update.patchUrl ), env->NewStringUTF( update.patchSha256 ), (jlong)update.patchSize, env->NewStringUTF( update.baseSha256 ));
	CZM_End( env );
}

static void CZM_CallVoid( const char *name )
{
	JNIEnv *env;
	jclass cls;
	jmethodID m;

	if( !CZM_Begin( &env, &cls ))
		return;
	m = CZM_Method( env, cls, name, "()V" );
	if( m )
		env->CallStaticVoidMethod( cls, m );
	CZM_End( env );
}

void CZM_UpdateInstall( void ) { CZM_CallVoid( "updateInstall" ); }
bool CZM_NetStoreUpdate( int *code, double *bytes )
{
	char text[64];

	*code = 0;
	*bytes = 0;
	CZM_CallString( "storeUpdateState", text, sizeof( text ));
	return sscanf( text, "%d %lf", code, bytes ) >= 1 && *code > 0;
}
void CZM_NetStoreUpdateStart( void ) { CZM_CallVoid( "storeUpdateStart" ); }
void CZM_UpdateCancel( void ) { CZM_CallVoid( "updateCancel" ); }
void CZM_UpdateCleanup( void ) { CZM_CallVoid( "updateCleanup" ); }

void CZM_UpdateState( int *state, double *done, double *total, char *error, size_t errorSize )
{
	char text[128];
	char why[32] = "";
	long long d = 0, t = 0;

	*state = 0;
	CZM_CallString( "updateState", text, sizeof( text ));
	sscanf( text, "%d %lld %lld %31s", state, &d, &t, why );
	*done = (double)d;
	*total = (double)t;
	Q_strncpy( error, why, errorSize );
}

#else // not Android: no network for the menu

bool CZM_NetAvailable( void ) { return false; }
bool CZM_CopyText( const char * ) { return false; }
void CZM_ServerAuthShow( const char *, const char * ) {}
void CZM_AccountShow( const char *, const char * ) {}
void CZM_AccountRegister( const char *, const char * ) {}
void CZM_AccountContext( const char *, const char * ) {}
void CZM_DistributionShow( const char *, const char * ) {}
void CZM_DistributionHelp( const char *, const char * ) {}
bool CZM_DistributionChanged( void ) { return false; }
bool CZM_AccountEvent( CUtlString & ) { return false; }
void CZM_LayoutsShow( void ) {}
bool CZM_WidgetEvent( CUtlString & ) { return false; }
bool CZM_CloudEvent( CUtlString & ) { return false; }
void CZM_CloudApplied( int, bool ) {}
void CZM_ColorPickerShow( int, int, int ) {}
bool CZM_ColorPickerEvent( int &, int &, int & ) { return false; }
void CZM_StartupReady( void ) {}
int CZM_NetRequest( const char *, const char *, const char *, const char * ) { return 0; }
int CZM_NetUpload( const char *, const char *, const char *, const char * ) { return 0; }
int CZM_NetDownload( const char *, const char * ) { return 0; }
bool CZM_NetPoll( int, int *status, CUtlString &body ) { *status = 0; body.Clear(); return true; }
const char *CZM_NetDeviceId( void ) { return ""; }
void CZM_NetNewKey( char *out, size_t size ) { if( size ) out[0] = 0; }
int CZM_NetVersionCode( void ) { return 0; }
bool CZM_NetCanSelfUpdate( void ) { return false; }
bool CZM_NetStoreUpdate( int *code, double *bytes ) { *code = 0; *bytes = 0; return false; }
void CZM_NetStoreUpdateStart( void ) {}
void CZM_UpdateStart( const CzmUpdateInfo & ) {}
void CZM_UpdateInstall( void ) {}
void CZM_UpdateCancel( void ) {}
void CZM_UpdateCleanup( void ) {}
void CZM_UpdateState( int *state, double *done, double *total, char *error, size_t size ) { *state = 0; *done = *total = 0; if( size ) error[0] = 0; }

#endif
