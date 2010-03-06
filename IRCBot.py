#!/usr/bin/env python

from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower, ip_numstr_to_quad, ip_quad_to_numstr
from DCHub import DCHubRemoteUser

class IRCChannelUser(object):
    def __init__(self, nick, **args):
        self.nick = nick
        self.is_hub = False
        self.is_op = False
        for key, value in args.items():
            setattr(self, key, value)
        
    def __eq__(self, other):
        if isinstance(other, basestring):
            return self.nick.lower() == other.lower()
        elif isinstance(other, IRCChannelUser):
            return self.nick.lower() == other.nick.lower()
        else:
            print "[IRCChannelUser:__eq__] got unknown object type: %r" % other
            return False
    
    def __str__(self):
        return self.nick

class IRCChannelUsers(object):
    def __init__(self):
        self.users = []
        
    def append(self, nick, **args):
        if IRCChannelUser(nick) in self.users: return False
        self.users.append(IRCChannelUser(nick, **args))
        print "[IRCChannelUsers] Added user: %r" % nick
        return True
    
    def remove(self, nick):
        if IRCChannelUser(nick) not in self: return False
        self.users.remove(IRCChannelUser(nick))
        print "[IRCChannelUsers] Removed user: %r" % nick
        return True
    
    def __contains__(self, nick):
        return IRCChannelUser(nick) in self.users
    
    def __getitem__(self, index):
        if isinstance(index, basestring):
            for user in self.users:
                if user == index: return user
            return None
        return self.users[index]

    def __len__(self):
        return len(self.users)

    def __str__(self):
        return "<'IRCChannelUsers' %s>" % self.users

class IRCBot(SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667, hub=None):
        SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self.connection.add_global_handler("all_events", self.on_all_events, -100)
        self.channel = channel
        self.chat_channel = "#pyIRDC"
        self.channel_users = IRCChannelUsers()
        self.send_queue = []
        self.hub = hub
    
    ### IRC Methods ###
    def format_message(self, msg):
        # remove new lines
        msg = msg.replace("\r", "").replace("\n", "")
        # remove message terminator
        msg = msg.replace("|", "")
        # convert back html escaped chars
        msg = msg.replace("&#36;", "$").replace("&#124;", "|")
        return msg
    
    def send_message(self, *args, **tokens):
        target, msgs = self.channel, args[0]
        if len(args) == 2:
            target = args[0]
            msgs = args[1]
        if type(msgs) != list: msgs = [str(msgs)]
        for msg in msgs: self.connection.privmsg(target, self.format_message(msg))

    def send_notice(self, target, msg, **tokens):
        msgs = msg
        if type(msg) != list: msgs = [str(msg)]
        for msg in msgs: self.connection.notice(target, self.format_message(msg))
    
    def process_once(self):
        for user in self.hub.remote_users:
            if not user.outgoing: continue
            print "sending msg to [%s]: %r" % (user.nick, user.outgoing)
            while len(user.outgoing) > 0:
                msg = user.outgoing[:400] # split on max size
                self.send_message(user.nick, msg)
                user.outgoing = user.outgoing[len(msg):]
            
        self.ircobj.process_once(0.15)
    
    @property
    def nickname(): return self.connection.get_nickname()
    ### Events ###
    def on_all_events(self, c, e):
        if e.eventtype() != "all_raw_messages":
            print e.source(), e.eventtype().upper(), e.target(), e.arguments()

    def on_welcome(self, c, e):
        c.join(self.channel, "$bong|")
        c.join(self.chat_channel)
    
    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")

    def on_nick(self, c, e):
        pass
    
    def on_join(self, c, e):
        if IRCChannelUser(nm_to_n(e.source())) == c.get_nickname(): return
        if e.target() == self.channel:
            self.channel_users.append(name, is_hub=True)
            self.add_user_to_hub(nm_to_n(e.source()), True)
    
    def on_part(self, c, e):
        if e.target() != self.channel: return
        self.on_quit(c, e)
    
    def on_quit(self, c, e):
        self.remove_user_from_hub(nm_to_n(e.source()))
    
    def on_privmsg(self, c, e):
        pass
    
    def on_pubmsg(self, c, e):
        nick = nm_to_n(e.source())
        msg = e.arguments()[0]
        if e.target() == self.channel:
            pass
        elif e.target() == self.chat_channel:
            self.hub.send_message("<%s> %s|" % (nick, msg))
    
    def on_action(self, c, e):
        if self.chat_channel and e.target() != self.chat_channel: return
        nick = nm_to_n(e.source())
        if not self.hub.local_user:
            print "[on_action] got NULL self.hub.localuser!"
            return
        self.hub.local_user.sendmessage("* %s %s|" % (nick, e.arguments()[0]))
    
    def on_namreply(self, c, e):
        for name in e.arguments()[2].split():
            is_op = name[0] in ['~', '&', '@', '%']
            name = name[1:] if is_op or name.startswith('+') else name
            if IRCChannelUser(name) == c.get_nickname(): continue
            if e.arguments()[1] == self.channel:
                print "[management] appending [%s] to channel_users..." % name
                self.channel_users.append(name, is_hub=(not is_op))
            
            elif e.arguments()[1] == self.chat_channel:
                print "[chat_channel] checking [%s]..." % name
                if not self.channel_users.append(name, is_op=is_op):
                    # update is_op if user was already in management channel
                    self.channel_users[name].is_op = is_op
                self.add_user_to_hub(name, self.channel_users[name].is_hub, is_op)
    
    def on_mode(self, c, e):
        nick = nm_to_n(e.source())
        if nick == c.get_nickname(): return
        args = e.arguments()[0]
        param = 0
        for mode in args:
            if mode == "+": add = True
            if mode == "-": add = False
            if mode.lower() in ['q', 'a', 'o', 'h']:
                if param - 1 >= len(e.arguments()):
                    print "[on_mode] Unable to parse mode. Breaking..."
                    break
                
                bot = self.hub.get_remote_user(e.arguments()[param])
                if add and not self.channel_users[e.arguments()[param]].is_op:
                    if e.target() == self.channel:
                        # user has been given ops in management channel
                        self.channel_users[e.arguments()[param]].is_hub = False
                        continue
                    
                    self.channel_users[e.arguments()[param]].is_op = True
                    if bot:
                        self.hub.ops[bot.nick] = bot
                        self.hub.giveOpList()
                    continue
                
                # nick is channel admin
                if add: continue
                # remove nick from channel admins
                self.channel_users[e.arguments()[param]].is_op = False
                if bot:
                    del self.hub.ops[bot.nick]
                    self.hub.giveOpList()
            param += 1

    def on_whoreply(self, c, e):
        nick = e.arguments()[1]
    
    def on_endofwho(self, c, e):
        nick = e.arguments()[0]
    
    ### Wrapper methods ###
    def add_user_to_hub(self, nick, is_hub=False, is_op=False):
        bot = DCHubRemoteUser(self.hub, nick, is_hub, is_op)
        # Make bot appear as a user to the hub
        if bot.nick in self.hub.nicks: bot.nick = bot.nick + "_"
        self.hub.nicks[bot.nick] = bot
        self.hub.users[bot.nick] = bot
        print 'RemoteUserBot logged in: %s' % bot.idstring
        self.hub.giveHello(bot, newuser=True)
        self.hub.giveMyINFO(bot)
        if is_op:
            self.hub.ops[bot.nick] = bot
            self.hub.giveOpList()
        self.hub.remote_users.append(bot)
    
    def remove_user_from_hub(self, nick):
        bot = self.hub.get_remote_user(nick)
        if not bot:
            print "[remove_user_from_hub] got NULL user"
            return
        self.hub.removeuser(bot)
        self.hub.remote_users.remove(bot)
