
import sys
if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol

import jpype
import org.hipparchus.filtering.kalman
import org.hipparchus.linear
import org.hipparchus.util
import typing



class UnscentedEvolution:
    """
    public class UnscentedEvolution extends :class:`~org.hipparchus.filtering.kalman.unscented.https:.docs.oracle.com.javase.8.docs.api.java.lang.Object?is`
    
        Container for :class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess` evolution data.
    
        Since:
            2.2
    
        Also see:
            :class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess`
    """
    def __init__(self, double: float, realVectorArray: typing.Union[typing.List[org.hipparchus.linear.RealVector], jpype.JArray]): ...
    def getCurrentStates(self) -> typing.MutableSequence[org.hipparchus.linear.RealVector]:
        """
            Get current states.
        
            Returns:
                current states
        
        
        """
        ...
    def getCurrentTime(self) -> float:
        """
            Get current time.
        
            Returns:
                current time
        
        
        """
        ...

_UnscentedKalmanFilter__T = typing.TypeVar('_UnscentedKalmanFilter__T', bound=org.hipparchus.filtering.kalman.Measurement)  # <T>
class UnscentedKalmanFilter(org.hipparchus.filtering.kalman.KalmanFilter[_UnscentedKalmanFilter__T], typing.Generic[_UnscentedKalmanFilter__T]):
    def __init__(self, matrixDecomposer: typing.Union[org.hipparchus.linear.MatrixDecomposer, typing.Callable], unscentedProcess: 'UnscentedProcess'[_UnscentedKalmanFilter__T], processEstimate: org.hipparchus.filtering.kalman.ProcessEstimate, unscentedTransformProvider: org.hipparchus.util.UnscentedTransformProvider): ...
    def estimationStep(self, t: _UnscentedKalmanFilter__T) -> org.hipparchus.filtering.kalman.ProcessEstimate: ...
    def getCorrected(self) -> org.hipparchus.filtering.kalman.ProcessEstimate: ...
    def getPredicted(self) -> org.hipparchus.filtering.kalman.ProcessEstimate: ...
    def getStateCrossCovariance(self) -> org.hipparchus.linear.RealMatrix: ...
    def getUnscentedTransformProvider(self) -> org.hipparchus.util.UnscentedTransformProvider: ...
    def setObserver(self, kalmanObserver: typing.Union[org.hipparchus.filtering.kalman.KalmanObserver, typing.Callable]) -> None: ...

_UnscentedProcess__T = typing.TypeVar('_UnscentedProcess__T', bound=org.hipparchus.filtering.kalman.Measurement)  # <T>
class UnscentedProcess(typing.Generic[_UnscentedProcess__T]):
    """
    public interface UnscentedProcess<T extends :class:`~org.hipparchus.filtering.kalman.Measurement`>
    
        Unscented process that can be estimated by a :class:`~org.hipparchus.filtering.kalman.unscented.UnscentedKalmanFilter`.
    
        This interface must be implemented by users to represent the behavior of the process to be estimated
    
        Since:
            2.2
    
        Also see:
            :class:`~org.hipparchus.filtering.kalman.unscented.UnscentedKalmanFilter`,
            :class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess`
    """
    def getEvolution(self, double: float, realVectorArray: typing.Union[typing.List[org.hipparchus.linear.RealVector], jpype.JArray], t: _UnscentedProcess__T) -> UnscentedEvolution:
        """
            Get the state evolution between two times.
        
            Parameters:
                previousTime (double): time of the previous state
                sigmaPoints (:class:`~org.hipparchus.filtering.kalman.unscented.https:.www.hipparchus.org.hipparchus`[]): sigma points
                measurement (:class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess`): measurement to process
        
            Returns:
                states evolution
        
        
        """
        ...
    def getInnovation(self, t: _UnscentedProcess__T, realVector: org.hipparchus.linear.RealVector, realVector2: org.hipparchus.linear.RealVector, realMatrix: org.hipparchus.linear.RealMatrix) -> org.hipparchus.linear.RealVector:
        """
            Get the innovation brought by a measurement.
        
            Parameters:
                measurement (:class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess`): measurement to process
                predictedMeasurement (:class:`~org.hipparchus.filtering.kalman.unscented.https:.www.hipparchus.org.hipparchus`): predicted measurement
                predictedState (:class:`~org.hipparchus.filtering.kalman.unscented.https:.www.hipparchus.org.hipparchus`): predicted state
                innovationCovarianceMatrix (:class:`~org.hipparchus.filtering.kalman.unscented.https:.www.hipparchus.org.hipparchus`): innovation covariance matrix
        
            Returns:
                innovation brought by a measurement, may be null if measurement should be rejected
        
        
        """
        ...
    def getPredictedMeasurements(self, realVectorArray: typing.Union[typing.List[org.hipparchus.linear.RealVector], jpype.JArray], t: _UnscentedProcess__T) -> typing.MutableSequence[org.hipparchus.linear.RealVector]:
        """
            Get the state evolution between two times.
        
            Parameters:
                predictedSigmaPoints (:class:`~org.hipparchus.filtering.kalman.unscented.https:.www.hipparchus.org.hipparchus`[]): predicted state sigma points
                measurement (:class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess`): measurement to process
        
            Returns:
                predicted measurement sigma points
        
        
        """
        ...
    def getProcessNoiseMatrix(self, double: float, realVector: org.hipparchus.linear.RealVector, t: _UnscentedProcess__T) -> org.hipparchus.linear.RealMatrix:
        """
            Get the process noise covariance corresponding to the state evolution between two times.
        
            Parameters:
                previousTime (double): time of the previous state
                predictedState (:class:`~org.hipparchus.filtering.kalman.unscented.https:.www.hipparchus.org.hipparchus`): predicted state
                measurement (:class:`~org.hipparchus.filtering.kalman.unscented.UnscentedProcess`): measurement to process
        
            Returns:
                states evolution
        
        
        """
        ...


class __module_protocol__(Protocol):
    # A module protocol which reflects the result of ``jp.JPackage("org.hipparchus.filtering.kalman.unscented")``.

    UnscentedEvolution: typing.Type[UnscentedEvolution]
    UnscentedKalmanFilter: typing.Type[UnscentedKalmanFilter]
    UnscentedProcess: typing.Type[UnscentedProcess]
