from __future__ import division
from .exceptions import (OutOfBoundsError,
                         VoidIntervalError,
                         UnsupportedPeriodError)
from .workshift import Workshift
from .core import _Frame, _check_groupby_freq

class Interval(object):
    """A series of workshifts within the timeboard.
    
    Interval is defined by two positions on the timeline which point to 
    the first and the last workshifts of the interval. An interval can
    contain one or more workshifts; empty interval is not allowed.
    
    Duty status of the workshifts within the interval is interpreted by the 
    given schedule.
    
    Parameters
    ----------
    timeboard : Timeboard
    bounds : a two-element sequence of int>=0 or Workshift
        The two elements of `bounds` provide the positions of the first and 
        the last workshifts of the interval within the timelime. The element's 
        type is either non-negative integer or an instance of Workshift.
    schedule: _Schedule, optional
        If not given, the timeboard's default schedule is used. 
    
    Raises
    ------
    VoidIntervalError (ValueError)
        If `bounds` are in the reverse order.
    OutOfBoundsError (LookupError)
        If any of `bounds` points outside the timeboard.
        
    Attributes
    ----------
    start_time : Timestamp
        When the first workshift of the interval starts.
    end_time : Timestamp
        When the last workshift of the interval ends.
    length : int
        Number of workshifts in the interval.
        
    Notes
    -----
    `get_interval` method of Timeboard class provides convenient ways to 
    instantiate an interval instead of calling Interval() constructor 
    directly. 
    """

    def __init__(self, timeboard, bounds, schedule=None):

        def handle_bound(bound):
            if isinstance(bound, Workshift):
                loc = bound._loc
            elif isinstance(bound, int):
                loc = bound
            else:
                raise TypeError('Interval bound = {}: expected integer or '
                                'Workshift, received {}'.
                                format(bound, type(bound)))
            if not 0 <= loc < len(timeboard._timeline):
                raise OutOfBoundsError("Interval bound {} is outside timeboard "
                                       "{}".format(bound, timeboard.compact_str))
            return loc

        if not hasattr(bounds, '__getitem__'):
            raise TypeError("'bounds' paramater must be list-like")

        try:
            bound0 = bounds[0]
            bound1 = bounds[1]
        except IndexError:
            raise IndexError("'bounds' value must contain two items")

        locs = (handle_bound(bound0), handle_bound(bound1))
        if locs[0] > locs[1]:
            raise VoidIntervalError('Attempted to create void interval with '
                                    '{!r}'.format(locs))
        self._tb = timeboard
        self._loc = locs
        self._length = self._loc[1] - self._loc[0] + 1
        if schedule is None:
            self._schedule = timeboard.default_schedule
        else:
            self._schedule = schedule
        self._duty_idx = {
            'on': self._schedule.on_duty_index,
            'off': self._schedule.off_duty_index,
            'any': self._schedule.index
        }
        self._duty_loc = {
            'on': self._find_my_bounds_in_idx(self._duty_idx['on']),
            'off': self._find_my_bounds_in_idx(self._duty_idx['off']),
            'any': self._loc
        }

    def _find_my_bounds_in_idx(self, idx):
        #TODO: optimize this search
        left_bound = 0
        len_idx = len(idx)
        while left_bound < len_idx and idx[left_bound] < self._loc[0]:
            left_bound += 1
        if left_bound == len_idx:
            return None, None
        right_bound = len(idx) - 1
        while right_bound >= left_bound and idx[right_bound] > self._loc[1]:
            right_bound -= 1
        if right_bound < left_bound:
            return None, None
        return left_bound, right_bound

    def __repr__(self):
        return self.compact_str

    @property
    def compact_str(self):
        return "Interval{!r}: {} -> {} [{}]".format(
            self._loc,
            Workshift(self._tb, self._loc[0]).compact_str,
            Workshift(self._tb, self._loc[1]).compact_str,
            self._length,
        )

    def __str__(self):
        return self.compact_str + "\n\n{}".format(
            self._tb.to_dataframe(self._loc[0], self._loc[1]))

    @property
    def start_time(self):
        # TODO: Refactor. This class has to know methods of Timeboard only
        return self._tb._timeline.get_ws_start_time(self._loc[0])

    @property
    def end_time(self):
        # TODO: Refactor. This class has to know methods of Timeboard only
        return self._tb._timeline.get_ws_end_time(self._loc[1])

    @property
    def length(self):
        """Number of workshifts in the interval."""
        return self._length

    #def labels(self):
    #    return self._tb._timeline.iloc[self._loc[0] : self._loc[1]+1]

    def first(self, duty='on'):
        """Return the first workshift with the specified duty.
        
        Same as `nth(1, duty)`
        
        See also:
        ---------
        nth : Return n-th workshift    
        """
        return self.nth(1, duty)

    def last(self, duty='on'):
        """Return the last workshift with the specified duty.
        
        Same as `nth(-1, duty)`
        
        See also:
        ---------
        nth : Return n-th workshift         
        """
        return self.nth(-1, duty)

    def nth(self, n, duty='on'):
        """Return n-th workshift with the specified `duty`.
        
        Parameters
        ----------
        n : int (!=0)
            Sequence number of the workshift within the interval. 
            Numbering starts at one. Negative values count from the end
            toward the beginning of the interval (n=-1 returns the last
            workshift). n=0 is not allowed.
            
        duty : {'on', 'off', 'any'} , optional (default 'on')
            Specify the duty of workshifts to be counted. If duty='on',
            off-duty workshifts are ignored, and vice versa. If duty='any',
            all workshifts are counted whatever the duty.
            
        Returns
        -------
        Workshift
        
        Raises
        ------
        OutOfBoundsError (LookupError)
            If the requested workshift does not exist within the interval.

        """
        try:
            duty_idx_bounds = self._duty_loc[duty]
            duty_idx = self._duty_idx[duty]
        except KeyError:
            raise ValueError('Invalid `duty` parameter {!r}'.format(duty))
        if duty_idx_bounds[0] is None or duty_idx_bounds[1] is None:
            return self._tb._handle_out_of_bounds(
                'Duty {!r} not found in interval {}'.format(duty,
                                                            self.compact_str))

        if n > 0:
            loc_in_duty_idx = duty_idx_bounds[0] + n - 1
        elif n < 0:
            loc_in_duty_idx = duty_idx_bounds[1] + n + 1
        else:
            raise ValueError("Parameter `n` must not be zero")

        if (loc_in_duty_idx < duty_idx_bounds[0] or
            loc_in_duty_idx > duty_idx_bounds[1]):

            return self._tb._handle_out_of_bounds(
                'No {} {!r} workshifts in the interval {}'.
                format(n, duty, self.compact_str))

        return Workshift(self._tb, duty_idx[loc_in_duty_idx], self._schedule)

    def count(self, duty='on'):
        """Return the count of workshifts with the specified duty.
        
        Parameters
        ----------
        duty : {'on', 'off', 'any'} , optional (default 'on')
            Specify the duty of workshifts to be counted. If duty='on',
            off-duty workshifts are ignored, and vice versa. If duty='any',
            all workshifts are counted whatever the duty.
            
        Returns
        -------
        int >=0
        """
        try:
            duty_idx_bounds = self._duty_loc[duty]
        except KeyError:
            raise ValueError('Invalid duty parameter {!r}'.format(duty))
        if duty_idx_bounds[0] is None or duty_idx_bounds[1] is None:
            return 0
        else:
            return duty_idx_bounds[1] - duty_idx_bounds[0] + 1

    def count_periods(self, period, duty='on'):
        """Return how many calendar periods fit into the interval.
        
        Parameters
        ----------
        period : str
            Pandas-compatible label defining a kind of calendar period 
            (i.e. 'M' for month). Pandas-native business periods (i.e. 'BM')  
            as well as  periods with multipliers (i.e. '3M') are not applicable.
        duty : {'on', 'off', 'any'} , optional (default 'on')
            Specify the duty of workshifts to be accounted for. See 'Notes'
            below for explanation.
            
        Returns
        -------
        float
            
        Raises
        ------
        OutOfBoundsError (LookupError)
            If the calendar period containing the first or the last 
            workshift of the interval (subject to duty) extends outside 
            the timeboard.
        UnsupportedPeriodError (ValueError)
            If `period` is not valid for this method or is not a multiple
            of timeboard's base unit.
        
        Notes
        -----
        The interval is sliced into calendar periods of the specified frequency
        and then each slice of the interval is compared to its corresponding 
        period duty-wise. That is to say, the count of workshifts in the 
        interval's slice is divided by the total count of workshifts in the 
        period containing this slice but only workshifts with the specified 
        duty are counted. The quotients for each period are summed to produce 
        the return value of the method.
        
        If a period does not contain workshifts of the required duty,
        it contributes zero to the returned value.
        
        Regardless of `period`, the method returns 0.0 if the interval 
        does not have workshifts with the specified duty.
        """
        SUPPORTED_PERIODS = ('S', 'T', 'min', 'H', 'D', 'W', 'M', 'Q', 'A', 'Y')
        #TODO: support shifted periods (i.e. W-TUE, A-MAR)
        if period not in SUPPORTED_PERIODS:
            raise UnsupportedPeriodError('Period {!r} is not supported'.
                                         format(period))
        if not _check_groupby_freq(self._tb.base_unit_freq, period):
            raise UnsupportedPeriodError('Period {!r} is not a superperiod '
                                         'of timeboard\'s base unit {!r}'.
                                         format(period, self._tb.base_unit_freq))
        try:
            ivl_duty_start_ts = self.first(duty).to_timestamp()
            ivl_duty_end_ts = self.last(duty).to_timestamp()
        except OutOfBoundsError:
            return 0.0

        period_index = _Frame(start=ivl_duty_start_ts, end=ivl_duty_end_ts,
                              base_unit_freq=period)
        first_period_ivl = self._tb.get_interval(
            period_index[0],
            clip_period=False, schedule=self._schedule)
        len_of_1st_period = first_period_ivl.count(duty=duty)
        last_period_ivl = self._tb.get_interval(
            period_index[-1],
            clip_period=False, schedule=self._schedule)
        len_of_last_period = last_period_ivl.count(duty=duty)

        if ivl_duty_end_ts <= period_index[0].end_time:
            ivl_units_in_only_period = self.count(duty=duty)
            return ivl_units_in_only_period / len_of_1st_period

        result = 0.0
        ivl_units_in_1st_period = self._tb.get_interval(
            (ivl_duty_start_ts, first_period_ivl.end_time),
            clip_period=False, schedule=self._schedule).count(duty=duty)
        result += ivl_units_in_1st_period / len_of_1st_period

        ivl_units_in_last_period = self._tb.get_interval(
            (last_period_ivl.start_time, ivl_duty_end_ts),
            clip_period=False, schedule=self._schedule).count(duty=duty)
        result += ivl_units_in_last_period / len_of_last_period

        full_periods_in_ivl = len(period_index) - 2
        if full_periods_in_ivl > 0:

            def duty_is_present(p):
                return self._tb.get_interval(
                    p,
                    clip_period=False,
                    schedule=self._schedule).count(duty=duty) > 0

            result += sum(map(duty_is_present, period_index[1:-1]))

        return result

    def where(self, ws, duty='same'):
        #TODO: Interval.where
        raise NotImplementedError

    def where_period(self, reference, period, duty='same'):
        #TODO: Interval.where_period
        raise NotImplementedError
